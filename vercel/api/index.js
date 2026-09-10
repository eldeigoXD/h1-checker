// Vercel Serverless Relay Handler for H1 Checker QA Tool
// Bridges remote requests on Vercel with your Home PC local worker.

const jobs = new Map();

// Clean up old jobs older than 30 minutes to keep memory clean
setInterval(() => {
  const now = Date.now();
  for (const [id, job] of jobs.entries()) {
    if (now - job.createdAt > 30 * 60 * 1000) {
      jobs.delete(id);
    }
  }
}, 5 * 60 * 1000);

let latestExtractedDeliverable = null;

let initialHistory = [];
try {
  initialHistory = require('./initial_history.json');
} catch (e) {
  initialHistory = [];
}

let historyDb = [...initialHistory];
let reportedBugsDb = [];
let imageBankDb = [];

function mergeImageAssets(newAssets) {
  if (!Array.isArray(newAssets)) return;
  newAssets.forEach(asset => {
    if (!asset || !asset.image_url) return;
    const existing = imageBankDb.find(a => a.image_url === asset.image_url);
    if (existing) {
      existing.use_count = Math.max(existing.use_count || 1, asset.use_count || 1);
      if (asset.make && asset.make !== 'unknown') existing.make = asset.make;
      if (asset.model && asset.model !== 'unknown') existing.model = asset.model;
      if (asset.condition && asset.condition !== 'general') existing.condition = asset.condition;
      if (asset.category && asset.category !== 'general') existing.category = asset.category;
      if (asset.alt_text) existing.alt_text = asset.alt_text;
      if (asset.section_title) existing.section_title = asset.section_title;
    } else {
      imageBankDb.push({
        id: asset.id || `IMG-${Date.now()}-${Math.random().toString(36).substr(2,4)}`,
        image_url: asset.image_url,
        make: asset.make || 'unknown',
        model: asset.model || 'unknown',
        condition: asset.condition || 'general',
        category: asset.category || 'general',
        surrounding_text: asset.surrounding_text || '',
        alt_text: asset.alt_text || '',
        section_title: asset.section_title || '',
        dealer_id: asset.dealer_id || '',
        use_count: asset.use_count || 1,
        first_seen: asset.first_seen || new Date().toISOString(),
        last_seen: new Date().toISOString()
      });
    }
  });
}

module.exports = async (req, res) => {
  // Enable CORS for all remote clients
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS,PATCH,DELETE,POST,PUT');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, X-Worker-Secret'
  );

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = url.pathname;
  const workerSecret = process.env.WORKER_SECRET_KEY || 'h1-checker-secret-key-2026';

  // Read request body helper for Vercel serverless
  let body = {};
  if (req.body) {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  }

  // 0. Bookmarklet Extracted Deliverable Store Endpoints
  if (pathname === '/api/save-extracted-dynamics') {
    latestExtractedDeliverable = {
      ...body,
      updatedAt: Date.now()
    };
    return res.status(200).json({ success: true, message: 'Extracted deliverable saved successfully' });
  }

  if (pathname === '/api/get-latest-dynamics') {
    if (!latestExtractedDeliverable) {
      return res.status(200).json({ success: false, message: 'No deliverable extracted yet' });
    }
    return res.status(200).json({ success: true, data: latestExtractedDeliverable });
  }

  // 0.5. Persistent Audit History Endpoints
  if (pathname === '/api/history' && req.method === 'GET') {
    const caseId = url.searchParams.get('id');
    if (caseId) {
      const item = historyDb.find(h => h.id === caseId || h.url === caseId);
      if (item) {
        return res.status(200).json({ success: true, data: item });
      }
      return res.status(404).json({ success: false, error: 'Case not found' });
    }
    return res.status(200).json(historyDb);
  }

  if ((pathname === '/api/save-history' || (pathname === '/api/history' && req.method === 'POST')) && req.method === 'POST') {
    const record = body;
    if (record && (record.id || record.url)) {
      let pathVal = record.path || '';
      if (!pathVal && record.url) {
        try { pathVal = new URL(record.url).pathname; } catch(e) {}
      }

      const historyEntry = {
        id: record.id || record.case_id || `D-${Date.now()}`,
        title: record.title || record.page_title || 'Scanned Page',
        url: record.url || record.completed_page_url || '',
        path: pathVal,
        timestamp: record.timestamp || Math.floor(Date.now() / 1000),
        has_bugs: Array.isArray(record.bugs) ? record.bugs.length > 0 : Boolean(record.has_bugs),
        bug_count: Array.isArray(record.bugs) ? record.bugs.length : (record.bug_count || 0),
        bugs: record.bugs || [],
        full_result: record.full_result || record
      };

      const existingIdx = historyDb.findIndex(h => (historyEntry.id && h.id === historyEntry.id) || (historyEntry.url && h.url === historyEntry.url));
      if (existingIdx >= 0) {
        historyDb[existingIdx] = historyEntry;
      } else {
        historyDb.unshift(historyEntry);
      }

      if (historyDb.length > 250) {
        historyDb = historyDb.slice(0, 250);
      }

      return res.status(200).json({ success: true, message: 'History record saved successfully' });
    }
    return res.status(400).json({ success: false, error: 'Invalid history record payload' });
  }

  // 0.6. Reported Tool Bugs Endpoints
  if (pathname === '/api/tool-bugs' && req.method === 'GET') {
    return res.status(200).json({ success: true, data: reportedBugsDb });
  }

  if ((pathname === '/api/report-bug' || pathname === '/api/tool-bugs') && req.method === 'POST') {
    const record = body;
    if (record && (record.url || record.case_id)) {
      const bugEntry = {
        id: record.id || `BUG-${Date.now()}`,
        case_id: record.case_id || 'N/A',
        url: record.url || '',
        title: record.title || record.page_title || '',
        path: record.path || '',
        user_comment: record.user_comment || '',
        timestamp: record.timestamp || Math.floor(Date.now() / 1000),
        full_scan_data: record.full_scan_data || {},
        debug_prompt: record.debug_prompt || ''
      };
      reportedBugsDb.unshift(bugEntry);
      if (reportedBugsDb.length > 100) {
        reportedBugsDb = reportedBugsDb.slice(0, 100);
      }
      return res.status(200).json({ success: true, message: 'Tool bug report submitted successfully', id: bugEntry.id });
    }
    return res.status(400).json({ success: false, error: 'Invalid bug report payload' });
  }

  if (pathname === '/api/tool-bugs' && req.method === 'DELETE') {
    const bugId = url.searchParams.get('id');
    if (bugId) {
      reportedBugsDb = reportedBugsDb.filter(b => b.id !== bugId);
      return res.status(200).json({ success: true, message: 'Bug report deleted' });
    }
    return res.status(400).json({ success: false, error: 'Missing bug ID' });
  }

  // 0.7. Image Bank API Endpoints & Sync
  if (pathname === '/api/image-bank/stats' && req.method === 'GET') {
    const makeCounts = {};
    const modelCounts = {};
    const categoryCounts = {};

    imageBankDb.forEach(asset => {
      if (asset.make && asset.make !== 'unknown') {
        makeCounts[asset.make] = (makeCounts[asset.make] || 0) + 1;
      }
      if (asset.model && asset.model !== 'unknown') {
        modelCounts[asset.model] = (modelCounts[asset.model] || 0) + 1;
      }
      if (asset.category) {
        categoryCounts[asset.category] = (categoryCounts[asset.category] || 0) + 1;
      }
    });

    const makes = Object.keys(makeCounts).map(m => ({ make: m, count: makeCounts[m] }));
    const models = Object.keys(modelCounts).map(m => ({ model: m, count: modelCounts[m] }));
    const categories = Object.keys(categoryCounts).map(c => ({ category: c, count: categoryCounts[c] }));

    return res.status(200).json({
      success: true,
      stats: {
        total_assets: imageBankDb.length,
        makes: makes,
        models: models,
        categories: categories
      }
    });
  }

  if (pathname === '/api/image-bank' && req.method === 'GET') {
    const make = url.searchParams.get('make');
    const model = url.searchParams.get('model');
    const condition = url.searchParams.get('condition');
    const category = url.searchParams.get('category');
    const search = url.searchParams.get('search');
    const limit = parseInt(url.searchParams.get('limit') || '50', 10);
    const offset = parseInt(url.searchParams.get('offset') || '0', 10);

    let filtered = [...imageBankDb];

    if (make) {
      filtered = filtered.filter(a => (a.make || '').toLowerCase() === make.toLowerCase());
    }
    if (model) {
      filtered = filtered.filter(a => (a.model || '').toLowerCase() === model.toLowerCase());
    }
    if (condition && condition.toLowerCase() !== 'all') {
      filtered = filtered.filter(a => (a.condition || '').toLowerCase() === condition.toLowerCase());
    }
    if (category && category.toLowerCase() !== 'all') {
      filtered = filtered.filter(a => (a.category || '').toLowerCase() === category.toLowerCase());
    }
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(a => 
        (a.surrounding_text || '').toLowerCase().includes(q) ||
        (a.alt_text || '').toLowerCase().includes(q) ||
        (a.section_title || '').toLowerCase().includes(q) ||
        (a.image_url || '').toLowerCase().includes(q)
      );
    }

    filtered.sort((a, b) => (b.use_count || 1) - (a.use_count || 1));

    const total = filtered.length;
    const paginated = filtered.slice(offset, offset + limit);

    return res.status(200).json({
      success: true,
      assets: paginated,
      total: total,
      limit: limit,
      offset: offset
    });
  }

  if ((pathname === '/api/image-bank/sync' || pathname === '/api/image-bank') && req.method === 'POST') {
    const newAssets = body.assets || (body.image_harvest ? body.image_harvest.harvested_assets : null) || body;
    if (Array.isArray(newAssets)) {
      mergeImageAssets(newAssets);
      return res.status(200).json({ success: true, message: `Synced ${newAssets.length} image assets`, total_in_db: imageBankDb.length });
    }
    return res.status(400).json({ success: false, error: 'Invalid assets payload' });
  }

  // 1. Worker Endpoints (Used by your Home PC local_worker.py)
  if (pathname === '/api/jobs/pending' || (pathname === '/api/jobs' && url.searchParams.get('action') === 'pending')) {
    const authHeader = req.headers['x-worker-secret'] || url.searchParams.get('key');
    if (authHeader !== workerSecret) {
      return res.status(401).json({ error: 'Unauthorized: Invalid worker secret key' });
    }

    // Find the oldest pending job
    for (const [id, job] of jobs.entries()) {
      if (job.status === 'pending') {
        job.status = 'processing';
        job.processingStartedAt = Date.now();
        return res.status(200).json({
          job_id: id,
          endpoint: job.endpoint,
          method: job.method,
          payload: job.payload,
          params: job.params
        });
      }
    }
    return res.status(200).json({ job_id: null });
  }

  if (pathname === '/api/jobs/complete' || (pathname === '/api/jobs' && url.searchParams.get('action') === 'complete')) {
    const authHeader = req.headers['x-worker-secret'] || url.searchParams.get('key');
    if (authHeader !== workerSecret) {
      return res.status(401).json({ error: 'Unauthorized: Invalid worker secret key' });
    }

    const { job_id, result, error } = body;
    if (!job_id || !jobs.has(job_id)) {
      return res.status(404).json({ error: 'Job not found' });
    }

    const job = jobs.get(job_id);
    if (error) {
      job.status = 'failed';
      job.error = error;
    } else {
      job.status = 'completed';
      job.result = result;

      // Automatically extract and store harvested images in Vercel Image Bank
      if (result && result.image_harvest && Array.isArray(result.image_harvest.harvested_assets)) {
        mergeImageAssets(result.image_harvest.harvested_assets);
      }
    }
    job.completedAt = Date.now();

    return res.status(200).json({ success: true, job_id });
  }

  // 2. Client Status Endpoint (Used by Remote PC UI to check progress)
  if (pathname === '/api/jobs/status' || (pathname === '/api/jobs' && url.searchParams.get('action') === 'status')) {
    const jobId = url.searchParams.get('job_id') || body.job_id;
    if (!jobId || !jobs.has(jobId)) {
      return res.status(404).json({ error: 'Job not found or expired' });
    }
    const job = jobs.get(jobId);
    return res.status(200).json({
      job_id: jobId,
      status: job.status,
      result: job.result || null,
      error: job.error || null,
      createdAt: job.createdAt,
      completedAt: job.completedAt || null
    });
  }

  // 3. Relay Job Creation Endpoints (Used by Remote PC UI to initiate scans)
  if (pathname.startsWith('/api/')) {
    const jobId = 'job_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
    const queryParams = {};
    for (const [k, v] of url.searchParams.entries()) {
      queryParams[k] = v;
    }

    jobs.set(jobId, {
      id: jobId,
      endpoint: pathname,
      method: req.method,
      payload: body,
      params: queryParams,
      status: 'pending',
      createdAt: Date.now()
    });

    return res.status(200).json({
      is_relay: true,
      job_id: jobId,
      status: 'pending',
      message: 'Scan request queued. Relay sending to Home PC for processing...'
    });
  }

  return res.status(404).json({ error: 'Endpoint not found' });
};

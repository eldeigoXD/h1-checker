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

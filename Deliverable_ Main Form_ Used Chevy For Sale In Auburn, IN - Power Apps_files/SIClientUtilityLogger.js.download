/**
 * @license Copyright (c) Microsoft Corporation.  All rights reserved.
 */
/// <reference path="../../../TypeDefinitions/mscrm.d.ts" />
//Only for UCI logs
var SIClientUtilityLogger;
(function (SIClientUtilityLogger) {
    ;
    var SITraceBIEventName = "SITraceBIEvent";
    var SITraceCIEventName = "SITraceCIEvent";
    var SITraceEventName = "SITraceEvent";
    var Telemetry = (function () {
        function Telemetry() {
        }
        // for example - values for FCB, org settings, user settings, etc.
        Telemetry.ReportInfo = function (params) {
            Telemetry.ReportLog(SITraceBIEventName, params);
        };
        // for example - values for user clicks, accept t&c etc.
        Telemetry.ReportUserAction = function (params) {
            Telemetry.ReportLog(SITraceCIEventName, params);
        };
        //log warnings 
        Telemetry.ReportWarning = function (params) {
            Telemetry.ReportLog(SITraceEventName, params, 2 /* Warning */);
        };
        //log errors
        Telemetry.ReportError = function (params) {
            Telemetry.ReportLog(SITraceEventName, params, 1 /* Error */);
        };
        Telemetry.ReportLog = function (eventName, params, level) {
            try {
                var reporting_1 = params && params.context && params.context.reporting ? params.context.reporting :
                    (Xrm && Xrm.Reporting ? Xrm.Reporting : null);
                var globalContext_1 = Xrm && Xrm.Utility && Xrm.Utility.getGlobalContext();
                globalContext_1 && globalContext_1.getCurrentAppName && globalContext_1.getCurrentAppName().then(function (appName) {
                    var applicationEvent = new Event(params.source, globalContext_1 && globalContext_1.organizationSettings &&
                        globalContext_1.organizationSettings.attributes && globalContext_1.organizationSettings.attributes['organizationId'], params.area, eventName, appName, params.action, params.actionOn, params.methodName, params.message, params.data, params.customControlId, level);
                    reporting_1 && reporting_1.reportEvent && reporting_1.reportEvent(applicationEvent);
                });
            }
            catch (ex) {
                console.error(ex);
            }
        };
        return Telemetry;
    }());
    SIClientUtilityLogger.Telemetry = Telemetry;
    var EventParameter = (function () {
        function EventParameter(name, value) {
            this.name = name;
            this.value = value;
        }
        return EventParameter;
    }());
    var Event = (function () {
        function Event(source, orgId, area, eventName, appName, action, actionOn, methodName, message, data, customControlId, level) {
            this.eventParameters = [];
            this.eventName = eventName;
            source && this.addEventParameter("Source", source);
            orgId && this.addEventParameter("OrgId", orgId);
            area && this.addEventParameter("Area", area);
            appName && this.addEventParameter("appName", appName);
            action && this.addEventParameter("Action", action);
            actionOn && this.addEventParameter("ActionOn", actionOn);
            methodName && this.addEventParameter("MethodName", methodName);
            message && this.addEventParameter("Message", message);
            data && this.addEventParameter("Data", this.SafeJsonStringify(data));
            customControlId && this.addEventParameter("CustomControlId", customControlId);
            level && this.addEventParameter("Level", level);
        }
        Event.prototype.addEventParameter = function (parameterName, value) {
            var event = new EventParameter(parameterName, value);
            this.eventParameters.push(event);
        };
        Event.prototype.SafeJsonStringify = function (data) {
            {
                try {
                    return JSON.stringify(data);
                }
                catch (ex) {
                    console.error(ex);
                    return "";
                }
            }
        };
        return Event;
    }());
})(SIClientUtilityLogger || (SIClientUtilityLogger = {}));

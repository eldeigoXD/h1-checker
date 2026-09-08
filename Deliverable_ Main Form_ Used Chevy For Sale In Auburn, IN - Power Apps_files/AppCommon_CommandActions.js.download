var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : new P(function (resolve) { resolve(result.value); }).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t;
    return { next: verb(0), "throw": verb(1), "return": verb(2) };
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = y[op[0] & 2 ? "return" : op[0] ? "throw" : "next"]) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [0, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
var ODataContract;
(function (ODataContract) {
    /* tslint:disable:crm-force-fields-private */
    var IsPdfEnabledForEntityRequest = (function () {
        function IsPdfEnabledForEntityRequest(enityLogicalName) {
            this.PDFSettingsEntityName = enityLogicalName;
        }
        IsPdfEnabledForEntityRequest.prototype.getMetadata = function () {
            var metadata = {
                boundParameter: null,
                operationName: "IsPdfEnabledForEntity",
                operationType: 0 /* Action */,
                parameterTypes: {
                    "PDFSettingsEntityName": {
                        "typeName": "Edm.String",
                        "structuralProperty": 1 /* PrimitiveType */,
                    }
                },
            };
            return metadata;
        };
        return IsPdfEnabledForEntityRequest;
    }());
    ODataContract.IsPdfEnabledForEntityRequest = IsPdfEnabledForEntityRequest;
})(ODataContract || (ODataContract = {}));
/**
* @license Copyright (c) Microsoft Corporation. All rights reserved.
*/
/// <reference path="../../../TypeDefinitions/CRM/ClientUtility.d.ts" />
/// <reference path="./DataContracts/IsPdfEnabledForEntity.ts" />
var AppCommon;
(function (AppCommon) {
    var _this = this;
    var CommandActions = (function () {
        function CommandActions() {
        }
        /*
         * The below api is used to Launch PDF dialog
         */
        CommandActions.LaunchPDFDialog = function () {
            // We will rely on infra events for any dialog launch failure which are unlikely to be due to pdf related issue.
            var dialogOptions = {
                width: 1090,
                height: 625,
                position: 1 /* center */
            };
            var dialogParams = {};
            var entityReference = Xrm.Page.data.entity.getEntityReference();
            dialogParams["param_entityId"] = entityReference.id;
            dialogParams["param_entityType"] = entityReference.entityType;
            dialogParams["param_entityTypeCode"] = Xrm.Internal.getEntityCode(entityReference.entityType);
            dialogParams["param_templateType"] = 2; // This is word document enum code
            dialogParams["param_documentType"] = "pdf";
            Xrm.Navigation.openDialog("ShowPDFPreview", dialogOptions, dialogParams);
        };
        return CommandActions;
    }());
    CommandActions.ConvertActivity = function (activityId, activityEntityName, targetEntity, targetEntityName, createCampaignResponse) {
        var request = new ODataContract.ConvertActivityRequest(activityId, activityEntityName, targetEntity, targetEntityName, createCampaignResponse);
        request.ActivityId = activityId;
        request.ActivityEntityName = activityEntityName;
        request.TargetEntity = targetEntity;
        request.TargetEntityName = targetEntityName;
        request.CreateCampaignResponse = createCampaignResponse;
        Xrm.WebApi.online.execute(request).then(function () { Xrm.Page.data.refresh(true); });
    };
    /*
    * custom rule To hide on salesPro
    */
    CommandActions.HideOnSalesPro = function () {
        if (!ClientUtility.ClientUtil.isUCI()) {
            return true;
        }
        return Xrm.Page.context.getCurrentAppProperties()
            .then(function (response) {
            if (response.uniqueName == "msdynce_salespro") {
                return false;
            }
            return true;
        }, function (err) {
            return true;
        });
    };
    AppCommon.CommandActions = CommandActions;
    var RibbonRules = (function () {
        function RibbonRules() {
        }
        return RibbonRules;
    }());
    RibbonRules.isPdfCommandEnabled = function (entity) { return __awaiter(_this, void 0, void 0, function () {
        var isPdfSettingEnabled, data, settingObject, settingValue, err_1;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    _a.trys.push([0, 3, , 4]);
                    isPdfSettingEnabled = sessionStorage.getItem(entity + "_isPdfSettingEnabled");
                    if (isPdfSettingEnabled) {
                        return [2 /*return*/, Boolean(isPdfSettingEnabled === "true")];
                    }
                    else if (!Mscrm.cachedPdf) {
                        Mscrm.cachedPdf = Xrm.WebApi.online.execute(new ODataContract.IsPdfEnabledForEntityRequest(entity));
                    }
                    return [4 /*yield*/, Mscrm.cachedPdf];
                case 1:
                    data = _a.sent();
                    return [4 /*yield*/, data.json()];
                case 2:
                    settingObject = _a.sent();
                    settingValue = settingObject["isPdfSettingEnabled"];
                    sessionStorage.setItem(entity + "_isPdfSettingEnabled", settingValue);
                    return [2 /*return*/, settingValue];
                case 3:
                    err_1 = _a.sent();
                    Xrm.Reporting.reportFailure("ExportToPdfButtonLoad", Error("Error while evaluating if button is enabled for entity: " + entity + ". Error: " + err_1.Message));
                    return [2 /*return*/, false];
                case 4: return [2 /*return*/];
            }
        });
    }); };
    AppCommon.RibbonRules = RibbonRules;
})(AppCommon || (AppCommon = {}));

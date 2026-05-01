import { useEffect, useMemo, useRef, useState } from "react";

import { fetchHealth, type HealthResponse } from "./api/health";
import {
  calculatePlanningRun,
  createPlannerOverride,
  createPlanningRun,
  fetchAssemblyRisk,
  fetchComponentStatus,
  fetchFlowBlockers,
  fetchLatestCalculatedPlanningRun,
  fetchMachineLoad,
  fetchMachineQueue,
  fetchPlannerOverrides,
  fetchPlanningRunDashboardSummary,
  fetchRecommendations,
  fetchValveReadiness,
  fetchVendorLoad,
  type AssemblyRiskItemResponse,
  type ComponentStatusListResponse,
  type FlowBlockerItemResponse,
  type MachineLoadSummaryResponse,
  type PlannerOverrideResponse,
  type PlanningRunDashboardSummaryResponse,
  type PlanningRunResponse,
  type QueueOperationListResponse,
  type RecommendationItemResponse,
  type VendorLoadItemResponse,
  type ValveReadinessItemResponse,
} from "./api/planningRuns";
import {
  ApiError,
  fetchValidationIssues,
  type UploadBatchResponse,
  type ValidationIssueResponse,
  type ValidationIssuesResponse,
  uploadWorkbook,
} from "./api/uploads";

type ConnectionState =
  | { status: "checking" }
  | { status: "connected"; health: HealthResponse }
  | { status: "unavailable" };

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | {
      status: "complete";
      upload: UploadBatchResponse;
      validation: ValidationIssuesResponse;
    }
  | {
      status: "validation-unavailable";
      upload: UploadBatchResponse;
      message: string;
    }
  | { status: "error"; message: string };

type ImplementedView = "Upload" | "Dashboard" | "Blockers" | "Machine Load" | "Valves" | "Recommendations";

type QueueState =
  | { status: "idle" }
  | { status: "loading"; machineType: string }
  | { status: "ready"; data: QueueOperationListResponse }
  | { status: "error"; machineType: string; message: string };

type MachineLoadViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      planningRun: PlanningRunResponse;
      machineLoad: MachineLoadSummaryResponse[];
      selectedMachineType: string;
      queue: QueueState;
    };

type ComponentStatusState =
  | { status: "idle" }
  | { status: "loading"; valveId: string }
  | { status: "ready"; data: ComponentStatusListResponse }
  | { status: "error"; valveId: string; message: string };

type ValveViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      planningRun: PlanningRunResponse;
      valveReadiness: ValveReadinessItemResponse[];
      assemblyRisk: AssemblyRiskItemResponse[];
      assemblyRiskMessage: string | null;
      selectedValveId: string;
      componentStatus: ComponentStatusState;
    };

type RecommendationViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      planningRun: PlanningRunResponse;
      recommendations: RecommendationItemResponse[];
      vendorLoad: VendorLoadItemResponse[];
      vendorLoadMessage: string | null;
      actionLog: PlannerOverrideResponse[];
      actionLogMessage: string | null;
    };

type DashboardViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      planningRun: PlanningRunResponse;
      summary: PlanningRunDashboardSummaryResponse;
    };

type BlockerViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "empty"; message: string }
  | { status: "error"; message: string }
  | {
      status: "ready";
      planningRun: PlanningRunResponse;
      blockers: FlowBlockerItemResponse[];
    };

type RecommendationActionDraft = {
  recommendationId: string;
  decisionMode: "ACCEPT" | "REJECT" | "OVERRIDE";
  overrideChoice: "FORCE_IN_HOUSE" | "FORCE_VENDOR" | "OVERRIDE";
  reason: string;
  remarks: string;
};

const navItems: Array<{ label: string; enabled: boolean; view?: ImplementedView }> = [
  { label: "Upload", enabled: true, view: "Upload" },
  { label: "Dashboard", enabled: true, view: "Dashboard" },
  { label: "Flow Blockers", enabled: true, view: "Blockers" },
  { label: "Machine Load", enabled: true, view: "Machine Load" },
  { label: "Valves", enabled: true, view: "Valves" },
  { label: "Recommendations", enabled: true, view: "Recommendations" },
  { label: "Reports", enabled: false },
];

function App() {
  const [activeView, setActiveView] = useState<ImplementedView>("Upload");
  const [connection, setConnection] = useState<ConnectionState>({ status: "checking" });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ status: "idle" });
  const [dashboardViewState, setDashboardViewState] = useState<DashboardViewState>({ status: "idle" });
  const [blockerViewState, setBlockerViewState] = useState<BlockerViewState>({ status: "idle" });
  const [machineLoadViewState, setMachineLoadViewState] = useState<MachineLoadViewState>({ status: "idle" });
  const [valveViewState, setValveViewState] = useState<ValveViewState>({ status: "idle" });
  const [recommendationViewState, setRecommendationViewState] = useState<RecommendationViewState>({ status: "idle" });
  const [recommendationActionDraft, setRecommendationActionDraft] = useState<RecommendationActionDraft | null>(null);
  const [recommendationActionMessage, setRecommendationActionMessage] = useState<string | null>(null);
  const [isSubmittingRecommendationAction, setIsSubmittingRecommendationAction] = useState(false);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [plannerMessage, setPlannerMessage] = useState<string | null>(null);
  const [isRetryingValidation, setIsRetryingValidation] = useState(false);
  const [isPlanningRunSetupOpen, setIsPlanningRunSetupOpen] = useState(false);
  const [planningStartDate, setPlanningStartDate] = useState("");
  const [planningHorizonDays, setPlanningHorizonDays] = useState<7 | 14>(7);
  const [isRunningPlanning, setIsRunningPlanning] = useState(false);
  const machineLoadRequestIdRef = useRef(0);
  const queueRequestIdRef = useRef(0);
  const valveViewRequestIdRef = useRef(0);
  const componentStatusRequestIdRef = useRef(0);
  const recommendationViewRequestIdRef = useRef(0);
  const dashboardViewRequestIdRef = useRef(0);
  const blockerViewRequestIdRef = useRef(0);
  const planningSetupUploadIdRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;

    fetchHealth()
      .then((health) => {
        if (active) {
          setConnection({ status: "connected", health });
        }
      })
      .catch(() => {
        if (active) {
          setConnection({ status: "unavailable" });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (activeView !== "Dashboard" || connection.status !== "connected") {
      return;
    }

    void loadDashboardWorkspace();
  }, [activeView, connection.status]);

  useEffect(() => {
    if (activeView !== "Blockers" || connection.status !== "connected") {
      return;
    }

    void loadBlockerWorkspace();
  }, [activeView, connection.status]);

  useEffect(() => {
    if (activeView !== "Machine Load" || connection.status !== "connected") {
      return;
    }

    void loadMachineLoadWorkspace();
  }, [activeView, connection.status]);

  useEffect(() => {
    if (activeView !== "Valves" || connection.status !== "connected") {
      return;
    }

    void loadValveWorkspace();
  }, [activeView, connection.status]);

  useEffect(() => {
    if (activeView !== "Recommendations" || connection.status !== "connected") {
      return;
    }

    void loadRecommendationWorkspace();
  }, [activeView, connection.status]);

  const validation = uploadState.status === "complete" ? uploadState.validation : null;
  const latestUpload =
    uploadState.status === "complete" || uploadState.status === "validation-unavailable"
      ? uploadState.upload
      : null;
  const blockingIssues = useMemo(
    () => validation?.issues.filter((issue) => issue.severity === "BLOCKING") ?? [],
    [validation],
  );
  const warningIssues = useMemo(
    () => validation?.issues.filter((issue) => issue.severity === "WARNING") ?? [],
    [validation],
  );
  const hasBlockingErrors = blockingIssues.length > 0;
  const canCreatePlanningRun =
    uploadState.status === "complete" &&
    uploadState.upload.status === "VALIDATED" &&
    !hasBlockingErrors &&
    connection.status === "connected";
  const validationPlaceholderMessage =
    uploadState.status === "uploading"
      ? "Validation details will appear after upload completes."
      : uploadState.status === "validation-unavailable"
        ? "Validation details are temporarily unavailable. Retry validation details to continue."
        : uploadState.status === "error"
          ? "Resolve the upload issue, then upload again to review validation results."
          : "Upload a workbook to review blocking errors and warnings.";

  useEffect(() => {
    if (latestUpload === null || planningSetupUploadIdRef.current === latestUpload.id) {
      return;
    }

    planningSetupUploadIdRef.current = latestUpload.id;
    setPlanningStartDate(latestUpload.uploaded_at.slice(0, 10));
    setPlanningHorizonDays(7);
    setIsPlanningRunSetupOpen(false);
    setPlannerMessage(null);
  }, [latestUpload]);

  async function loadValidationDetails(upload: UploadBatchResponse, options?: { retry?: boolean }) {
    if (options?.retry) {
      setIsRetryingValidation(true);
    }

    try {
      const validationIssues = await fetchValidationIssues(upload.id);
      setUploadState({
        status: "complete",
        upload,
        validation: validationIssues,
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Upload completed, but validation details could not be loaded. Retry validation before planning.";
      setUploadState({
        status: "validation-unavailable",
        upload,
        message,
      });
    } finally {
      if (options?.retry) {
        setIsRetryingValidation(false);
      }
    }
  }

  async function loadDashboardWorkspace() {
    const dashboardViewRequestId = dashboardViewRequestIdRef.current + 1;
    dashboardViewRequestIdRef.current = dashboardViewRequestId;
    setDashboardViewState({ status: "loading" });

    try {
      const planningRun = await fetchLatestCalculatedPlanningRun();
      if (dashboardViewRequestId !== dashboardViewRequestIdRef.current) {
        return;
      }

      if (!planningRun) {
        setDashboardViewState({
          status: "empty",
          message: "No calculated planning run yet. Finish planning run setup and calculation first.",
        });
        return;
      }

      const summary = await fetchPlanningRunDashboardSummary(planningRun.id);
      if (dashboardViewRequestId !== dashboardViewRequestIdRef.current) {
        return;
      }

      setDashboardViewState({
        status: "ready",
        planningRun,
        summary,
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Home dashboard could not be loaded. Retry when the API is ready.";
      setDashboardViewState({ status: "error", message });
    }
  }

  async function loadBlockerWorkspace() {
    const blockerViewRequestId = blockerViewRequestIdRef.current + 1;
    blockerViewRequestIdRef.current = blockerViewRequestId;
    setBlockerViewState({ status: "loading" });

    try {
      const planningRun = await fetchLatestCalculatedPlanningRun();
      if (blockerViewRequestId !== blockerViewRequestIdRef.current) {
        return;
      }

      if (!planningRun) {
        setBlockerViewState({
          status: "empty",
          message: "No calculated planning run yet. Finish planning run setup and calculation first.",
        });
        return;
      }

      const flowBlockers = await fetchFlowBlockers(planningRun.id);
      if (blockerViewRequestId !== blockerViewRequestIdRef.current) {
        return;
      }

      if (flowBlockers.items.length === 0) {
        setBlockerViewState({
          status: "empty",
          message: "Latest calculated planning run does not have active flow blockers.",
        });
        return;
      }

      setBlockerViewState({
        status: "ready",
        planningRun,
        blockers: flowBlockers.items,
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Flow blockers could not be loaded. Retry when the API is ready.";
      setBlockerViewState({ status: "error", message });
    }
  }

  async function handlePlanningRunSetup() {
    if (!canCreatePlanningRun || uploadState.status !== "complete") {
      return;
    }

    if (!planningStartDate) {
      setPlannerMessage("Planning start date is required.");
      return;
    }

    setIsRunningPlanning(true);
    setPlannerMessage(null);

    try {
      const planningRun = await createPlanningRun({
        upload_batch_id: uploadState.upload.id,
        planning_start_date: planningStartDate,
        planning_horizon_days: planningHorizonDays,
      });
      await calculatePlanningRun(planningRun.id);
      setPlannerMessage("Planning run calculated. Opening dashboard...");
      setIsPlanningRunSetupOpen(false);
      setActiveView("Dashboard");
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Planning run could not be created and calculated.";
      setPlannerMessage(message);
    } finally {
      setIsRunningPlanning(false);
    }
  }

  async function loadMachineLoadWorkspace() {
    const machineLoadRequestId = machineLoadRequestIdRef.current + 1;
    machineLoadRequestIdRef.current = machineLoadRequestId;
    queueRequestIdRef.current += 1;
    setMachineLoadViewState({ status: "loading" });

    try {
      const planningRun = await fetchLatestCalculatedPlanningRun();
      if (machineLoadRequestId !== machineLoadRequestIdRef.current) {
        return;
      }
      if (!planningRun) {
        setMachineLoadViewState({
          status: "empty",
          message: "No calculated planning run yet. Finish planning run setup and calculation first.",
        });
        return;
      }

      const machineLoad = await fetchMachineLoad(planningRun.id);
      if (machineLoadRequestId !== machineLoadRequestIdRef.current) {
        return;
      }
      if (machineLoad.items.length === 0) {
        setMachineLoadViewState({
          status: "empty",
          message: "Latest calculated planning run does not have machine load rows yet.",
        });
        return;
      }

      const selectedMachineType = machineLoad.items[0].machine_type;
      setMachineLoadViewState({
        status: "ready",
        planningRun,
        machineLoad: machineLoad.items,
        selectedMachineType,
          queue: { status: "loading", machineType: selectedMachineType },
      });
      await loadMachineQueueDetails(planningRun.id, selectedMachineType);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Latest calculated planning run could not be loaded. Retry when the API is ready.";
      setMachineLoadViewState({ status: "error", message });
    }
  }

  async function loadMachineQueueDetails(planningRunId: string, machineType: string) {
    const queueRequestId = queueRequestIdRef.current + 1;
    queueRequestIdRef.current = queueRequestId;

    setMachineLoadViewState((current) =>
      current.status !== "ready"
        ? current
        : {
            ...current,
            selectedMachineType: machineType,
            queue: { status: "loading", machineType },
          },
    );

    try {
      const queue = await fetchMachineQueue(planningRunId, machineType);
      setMachineLoadViewState((latest) =>
        queueRequestId !== queueRequestIdRef.current ||
        latest.status !== "ready" ||
        latest.planningRun.id !== planningRunId ||
        latest.selectedMachineType !== machineType
          ? latest
          : {
              ...latest,
              selectedMachineType: machineType,
              queue: { status: "ready", data: queue },
            },
      );
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Machine queue could not be loaded.";
      setMachineLoadViewState((latest) =>
        queueRequestId !== queueRequestIdRef.current ||
        latest.status !== "ready" ||
        latest.planningRun.id !== planningRunId ||
        latest.selectedMachineType !== machineType
          ? latest
          : {
              ...latest,
              selectedMachineType: machineType,
              queue: { status: "error", machineType, message },
            },
      );
    }
  }

  async function loadValveWorkspace() {
    const valveViewRequestId = valveViewRequestIdRef.current + 1;
    valveViewRequestIdRef.current = valveViewRequestId;
    componentStatusRequestIdRef.current += 1;
    setValveViewState({ status: "loading" });

    try {
      const planningRun = await fetchLatestCalculatedPlanningRun();
      if (valveViewRequestId !== valveViewRequestIdRef.current) {
        return;
      }

      if (!planningRun) {
        setValveViewState({
          status: "empty",
          message: "No calculated planning run yet. Finish planning run setup and calculation first.",
        });
        return;
      }

      const [valveReadinessResult, assemblyRiskResult] = await Promise.allSettled([
        fetchValveReadiness(planningRun.id),
        fetchAssemblyRisk(planningRun.id),
      ]);
      if (valveViewRequestId !== valveViewRequestIdRef.current) {
        return;
      }

      if (valveReadinessResult.status !== "fulfilled") {
        const message =
          valveReadinessResult.reason instanceof ApiError
            ? valveReadinessResult.reason.message
            : "Valve readiness could not be loaded. Retry when the API is ready.";
        setValveViewState({ status: "error", message });
        return;
      }

      const valveReadiness = valveReadinessResult.value;
      if (valveReadiness.items.length === 0) {
        setValveViewState({
          status: "empty",
          message: "Latest calculated planning run does not have valve readiness rows yet.",
        });
        return;
      }

      const assemblyRisk =
        assemblyRiskResult.status === "fulfilled" ? assemblyRiskResult.value.items : [];
      const assemblyRiskMessage =
        assemblyRiskResult.status === "fulfilled"
          ? null
          : assemblyRiskResult.reason instanceof ApiError
            ? assemblyRiskResult.reason.message
            : "Assembly risk could not be loaded. Valve readiness is still available.";
      const selectedValveId = valveReadiness.items[0].valve_id;
      setValveViewState({
        status: "ready",
        planningRun,
        valveReadiness: valveReadiness.items,
        assemblyRisk,
        assemblyRiskMessage,
        selectedValveId,
        componentStatus: { status: "loading", valveId: selectedValveId },
      });

      await loadComponentStatusDetails(planningRun.id, selectedValveId);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Valve readiness and assembly risk could not be loaded. Retry when the API is ready.";
      setValveViewState({ status: "error", message });
    }
  }

  async function loadComponentStatusDetails(planningRunId: string, valveId: string) {
    const componentStatusRequestId = componentStatusRequestIdRef.current + 1;
    componentStatusRequestIdRef.current = componentStatusRequestId;

    setValveViewState((current) =>
      current.status !== "ready"
        ? current
        : {
            ...current,
            selectedValveId: valveId,
            componentStatus: { status: "loading", valveId },
          },
    );

    try {
      const componentStatus = await fetchComponentStatus(planningRunId, valveId);
      setValveViewState((latest) =>
        componentStatusRequestId !== componentStatusRequestIdRef.current ||
        latest.status !== "ready" ||
        latest.planningRun.id !== planningRunId ||
        latest.selectedValveId !== valveId
          ? latest
          : {
              ...latest,
              selectedValveId: valveId,
              componentStatus: { status: "ready", data: componentStatus },
            },
      );
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Component status could not be loaded.";
      setValveViewState((latest) =>
        componentStatusRequestId !== componentStatusRequestIdRef.current ||
        latest.status !== "ready" ||
        latest.planningRun.id !== planningRunId ||
        latest.selectedValveId !== valveId
          ? latest
          : {
              ...latest,
              selectedValveId: valveId,
              componentStatus: { status: "error", valveId, message },
            },
      );
    }
  }

  async function loadRecommendationWorkspace() {
    const recommendationViewRequestId = recommendationViewRequestIdRef.current + 1;
    recommendationViewRequestIdRef.current = recommendationViewRequestId;
    setRecommendationViewState({ status: "loading" });
    setRecommendationActionDraft(null);
    setRecommendationActionMessage(null);

    try {
      const planningRun = await fetchLatestCalculatedPlanningRun();
      if (recommendationViewRequestId !== recommendationViewRequestIdRef.current) {
        return;
      }

      if (!planningRun) {
        setRecommendationViewState({
          status: "empty",
          message: "No calculated planning run yet. Finish planning run setup and calculation first.",
        });
        return;
      }

      const [recommendationsResult, vendorLoadResult, actionLogResult] = await Promise.allSettled([
        fetchRecommendations(planningRun.id),
        fetchVendorLoad(planningRun.id),
        fetchPlannerOverrides(planningRun.id),
      ]);
      if (recommendationViewRequestId !== recommendationViewRequestIdRef.current) {
        return;
      }

      if (recommendationsResult.status !== "fulfilled") {
        const message =
          recommendationsResult.reason instanceof ApiError
            ? recommendationsResult.reason.message
            : "Recommendations could not be loaded. Retry when the API is ready.";
        setRecommendationViewState({ status: "error", message });
        return;
      }

      setRecommendationViewState({
        status: "ready",
        planningRun,
        recommendations: [...recommendationsResult.value.items],
        vendorLoad: vendorLoadResult.status === "fulfilled" ? [...vendorLoadResult.value.items] : [],
        vendorLoadMessage:
          vendorLoadResult.status === "fulfilled"
            ? null
            : vendorLoadResult.reason instanceof ApiError
              ? vendorLoadResult.reason.message
              : "Vendor exposure could not be loaded. Recommendations are still available.",
        actionLog: actionLogResult.status === "fulfilled" ? [...actionLogResult.value.overrides] : [],
        actionLogMessage:
          actionLogResult.status === "fulfilled"
            ? null
            : actionLogResult.reason instanceof ApiError
              ? actionLogResult.reason.message
              : "Planner action log could not be loaded. Recommendation review is still available.",
      });
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Recommendation review could not be loaded. Retry when the API is ready.";
      setRecommendationViewState({ status: "error", message });
    }
  }

  function startRecommendationAction(
    recommendationId: string,
    decisionMode: RecommendationActionDraft["decisionMode"],
  ) {
    setRecommendationActionMessage(null);
    setRecommendationActionDraft({
      recommendationId,
      decisionMode,
      overrideChoice: "FORCE_IN_HOUSE",
      reason: "",
      remarks: "",
    });
  }

  async function submitRecommendationAction() {
    if (recommendationViewState.status !== "ready" || recommendationActionDraft === null) {
      return;
    }

    const planningRunId = recommendationViewState.planningRun.id;
    const recommendation = recommendationViewState.recommendations.find(
      (row) => row.id === recommendationActionDraft.recommendationId,
    );
    if (!recommendation) {
      setRecommendationActionMessage("Recommendation context was lost. Refresh recommendations and try again.");
      return;
    }

    const reason = recommendationActionDraft.reason.trim();
    if (reason.length === 0) {
      setRecommendationActionMessage("Reason is required before saving a planner decision.");
      return;
    }

    const remarks =
      recommendationActionDraft.remarks.trim().length > 0 ? recommendationActionDraft.remarks.trim() : null;
    const overrideDecision =
      recommendationActionDraft.decisionMode === "OVERRIDE"
        ? recommendationActionDraft.overrideChoice
        : recommendationActionDraft.decisionMode;

    setIsSubmittingRecommendationAction(true);
    setRecommendationActionMessage(null);

    try {
      const override = await createPlannerOverride({
        planning_run_id: planningRunId,
        entity_type: "RECOMMENDATION",
        entity_id: recommendation.id,
        original_recommendation: recommendation.recommendation_type,
        override_decision: overrideDecision,
        reason,
        remarks,
      });

      setRecommendationViewState((current) =>
        current.status !== "ready" || current.planningRun.id !== planningRunId
          ? current
          : {
              ...current,
              recommendations: current.recommendations.map((row) =>
                row.id !== recommendation.id
                  ? row
                  : {
                      ...row,
                      status: recommendationStatusForOverrideDecision(override.override_decision),
                    },
              ),
              actionLog: [override, ...current.actionLog],
            },
      );
      setRecommendationActionDraft(null);
      setRecommendationActionMessage("Decision recorded.");
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Planner decision could not be recorded.";
      setRecommendationActionMessage(message);
    } finally {
      setIsSubmittingRecommendationAction(false);
    }
  }

  async function handleUploadSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPlannerMessage(null);
    setIsPlanningRunSetupOpen(false);

    if (connection.status === "unavailable") {
      setUploadState({ status: "error", message: "Backend unavailable. Start the API and refresh." });
      return;
    }

    if (!selectedFile) {
      setFileMessage("Choose the latest .xlsx workbook before uploading.");
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".xlsx")) {
      setFileMessage("Only .xlsx workbooks are supported.");
      return;
    }

    setFileMessage(null);
    setUploadState({ status: "uploading" });

    try {
      const upload = await uploadWorkbook(selectedFile);
      await loadValidationDetails(upload);
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Upload failed. Please try again with the standard workbook.";
      setUploadState({ status: "error", message });
    }
  }

  function handleFileSelection(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setPlannerMessage(null);
    setIsPlanningRunSetupOpen(false);
    setUploadState({ status: "idle" });

    if (!file) {
      setFileMessage("Choose the latest .xlsx workbook before uploading.");
      return;
    }

    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setFileMessage("Only .xlsx workbooks are supported.");
      return;
    }

    setFileMessage(null);
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Machine shop planning</p>
          <h1>Production Planning AI</h1>
        </div>
        <ConnectionBadge connection={connection} />
      </header>

      <nav className="primary-nav" aria-label="Primary navigation">
        {navItems.map((item) => (
          <button
            className={item.view === activeView ? "nav-item active" : "nav-item"}
            disabled={!item.enabled}
            key={item.label}
            onClick={() => {
              if (item.view) {
                setActiveView(item.view);
              }
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </nav>

      {activeView === "Upload" ? (
        <>
          <section className="workspace" aria-labelledby="workspace-title">
            <div className="workspace-main">
              <div className="workspace-copy">
                <p className="eyebrow">Data upload</p>
                <h2 id="workspace-title">Upload the latest planning workbook and review validation before planning.</h2>
                <p className="workspace-intro">
                  Keep the first move simple: upload the standard `.xlsx`, separate blocking errors from warnings, then
                  continue only when the workbook is fit to plan.
                </p>
              </div>

              <form className="upload-band" onSubmit={handleUploadSubmit}>
                <div className="field-row">
                  <label className="field-label" htmlFor="upload-workbook">
                    Upload workbook
                  </label>
                  <input
                    accept=".xlsx"
                    className="file-input"
                    id="upload-workbook"
                    onChange={handleFileSelection}
                    type="file"
                  />
                  <p className="field-help">Use the standard `.xlsx` workbook. Other spreadsheet formats are rejected.</p>
                  {fileMessage ? <p className="field-error">{fileMessage}</p> : null}
                </div>

                <div className="action-row">
                  <button
                    className="primary-button"
                    disabled={uploadState.status === "uploading" || connection.status === "unavailable"}
                    type="submit"
                  >
                    {uploadState.status === "uploading" ? "Uploading workbook..." : "Upload workbook"}
                  </button>
                  <button
                    className="secondary-button"
                    disabled={!canCreatePlanningRun}
                    onClick={() => {
                      setIsPlanningRunSetupOpen(true);
                      setPlannerMessage(null);
                    }}
                    type="button"
                  >
                    Planning run setup next
                  </button>
                </div>

                {isPlanningRunSetupOpen ? (
                  <div className="planning-setup">
                    <div className="validation-section-header">
                      <h4>Planning run setup</h4>
                      <span>{planningHorizonDays} days</span>
                    </div>

                    <div className="action-form-grid">
                      <label className="field-label">
                        Planning start date
                        <input
                          className="text-input"
                          onChange={(event) => setPlanningStartDate(event.target.value)}
                          type="date"
                          value={planningStartDate}
                        />
                      </label>

                      <label className="field-label">
                        Planning horizon
                        <select
                          className="text-input"
                          onChange={(event) => setPlanningHorizonDays(Number(event.target.value) as 7 | 14)}
                          value={planningHorizonDays}
                        >
                          <option value={7}>7 days</option>
                          <option value={14}>14 days</option>
                        </select>
                      </label>
                    </div>

                    <p className="field-help">
                      Default planning start date uses the upload date. Horizon drives the throughput target and look-ahead window.
                    </p>

                    <div className="action-row">
                      <button
                        className="primary-button"
                        disabled={!canCreatePlanningRun || isRunningPlanning}
                        onClick={() => void handlePlanningRunSetup()}
                        type="button"
                      >
                        {isRunningPlanning ? "Creating and calculating..." : "Create and run planning"}
                      </button>
                      <button
                        className="secondary-button"
                        disabled={isRunningPlanning}
                        onClick={() => {
                          setIsPlanningRunSetupOpen(false);
                          setPlannerMessage(null);
                        }}
                        type="button"
                      >
                        Close setup
                      </button>
                    </div>
                  </div>
                ) : null}

                {uploadState.status === "validation-unavailable" ? (
                  <div className="action-row">
                    <button
                      className="secondary-button"
                      disabled={isRetryingValidation}
                      onClick={() => void loadValidationDetails(uploadState.upload, { retry: true })}
                      type="button"
                    >
                      {isRetryingValidation ? "Retrying validation details..." : "Retry validation details"}
                    </button>
                  </div>
                ) : null}

                {uploadState.status === "uploading" ? (
                  <div aria-live="polite" className="progress-band" role="status">
                    <span>Uploading workbook and validating rows...</span>
                    <div aria-hidden="true" className="progress-track">
                      <div className="progress-indicator" />
                    </div>
                  </div>
                ) : null}

                <UploadFeedback uploadState={uploadState} />
                {plannerMessage ? <p className="planner-note">{plannerMessage}</p> : null}
              </form>
            </div>

            <aside className="workspace-side" aria-label="Upload status">
              <StatusStack
                items={[
                  {
                    label: "Backend",
                    value:
                      connection.status === "connected"
                        ? `${connection.health.environment} ready`
                        : connection.status === "checking"
                          ? "Checking"
                          : "Unavailable",
                  },
                  {
                    label: "Workbook",
                    value: latestUpload?.original_filename ?? selectedFile?.name ?? "Nothing selected",
                  },
                  {
                    label: "Planning run",
                    value:
                      uploadState.status === "validation-unavailable"
                        ? "Waiting on validation details"
                        : canCreatePlanningRun
                          ? "Ready to continue"
                          : "Waiting on validation",
                  },
                ]}
              />

              {latestUpload ? (
                <UploadSummary upload={latestUpload} validation={validation} />
              ) : (
                <div className="side-note">
                  <h3>What we check first</h3>
                  <ul>
                    <li>Workbook format is `.xlsx`.</li>
                    <li>Blocking errors stay separate from warnings.</li>
                    <li>Planning stays blocked until blocking issues are gone.</li>
                  </ul>
                </div>
              )}
            </aside>
          </section>

          <section className="validation-layout" aria-labelledby="validation-title">
            <div className="validation-header">
              <p className="eyebrow">Validation review</p>
              <h3 id="validation-title">Read blocking issues first, then decide whether warnings can wait.</h3>
            </div>

            {validation ? (
              <>
                <ValidationSection
                  emptyMessage="No blocking errors."
                  issues={blockingIssues}
                  title="Blocking errors"
                />
                <ValidationSection emptyMessage="No warnings." issues={warningIssues} title="Warnings" />
              </>
            ) : (
              <ValidationPlaceholder message={validationPlaceholderMessage} />
            )}
          </section>
        </>
      ) : activeView === "Dashboard" ? (
        <DashboardWorkspace
          connection={connection}
          dashboardViewState={dashboardViewState}
          onOpenBlockers={() => setActiveView("Blockers")}
          onOpenMachineLoad={() => setActiveView("Machine Load")}
          onOpenRecommendations={() => setActiveView("Recommendations")}
          onOpenValves={() => setActiveView("Valves")}
          onRefresh={() => void loadDashboardWorkspace()}
        />
      ) : activeView === "Blockers" ? (
        <BlockerWorkspace
          blockerViewState={blockerViewState}
          connection={connection}
          onRefresh={() => void loadBlockerWorkspace()}
        />
      ) : activeView === "Machine Load" ? (
        <MachineLoadWorkspace
          connection={connection}
          machineLoadViewState={machineLoadViewState}
          onOpenQueue={(machineType) =>
            machineLoadViewState.status === "ready"
              ? void loadMachineQueueDetails(machineLoadViewState.planningRun.id, machineType)
              : undefined
          }
          onRefresh={() => void loadMachineLoadWorkspace()}
        />
      ) : activeView === "Valves" ? (
        <ValveWorkspace
          connection={connection}
          valveViewState={valveViewState}
          onOpenComponentStatus={(valveId) =>
            valveViewState.status === "ready"
              ? void loadComponentStatusDetails(valveViewState.planningRun.id, valveId)
              : undefined
          }
          onRefresh={() => void loadValveWorkspace()}
        />
      ) : (
        <RecommendationWorkspace
          connection={connection}
          recommendationActionDraft={recommendationActionDraft}
          recommendationActionMessage={recommendationActionMessage}
          recommendationViewState={recommendationViewState}
          isSubmittingRecommendationAction={isSubmittingRecommendationAction}
          onActionDraftChange={setRecommendationActionDraft}
          onCancelAction={() => {
            setRecommendationActionDraft(null);
            setRecommendationActionMessage(null);
          }}
          onRefresh={() => void loadRecommendationWorkspace()}
          onStartAction={startRecommendationAction}
          onSubmitAction={() => void submitRecommendationAction()}
        />
      )}
    </main>
  );
}

function UploadFeedback({ uploadState }: { uploadState: UploadState }) {
  if (uploadState.status === "error") {
    return <p className="feedback-banner error">{uploadState.message}</p>;
  }

  if (uploadState.status === "validation-unavailable") {
    return <p className="feedback-banner warning">{uploadState.message}</p>;
  }

  if (uploadState.status !== "complete") {
    return null;
  }

  if (uploadState.validation.summary.blocking > 0) {
    return <p className="feedback-banner error">Upload has blocking errors. Fix the highlighted rows and upload again.</p>;
  }

  return <p className="feedback-banner success">Upload validated. Ready to create planning run.</p>;
}

function UploadSummary({
  upload,
  validation,
}: {
  upload: UploadBatchResponse;
  validation: ValidationIssuesResponse | null;
}) {
  return (
    <div className="side-summary">
      <h3>Latest upload</h3>
      <dl className="summary-grid">
        <div>
          <dt>File</dt>
          <dd>{upload.original_filename}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{upload.status}</dd>
        </div>
        <div>
          <dt>Blocking</dt>
          <dd>{validation?.summary.blocking ?? upload.validation_error_count}</dd>
        </div>
        <div>
          <dt>Warnings</dt>
          <dd>{validation?.summary.warning ?? upload.validation_warning_count}</dd>
        </div>
      </dl>
    </div>
  );
}

function ValidationPlaceholder({ message }: { message: string }) {
  return (
    <section className="validation-section" aria-label="Validation details unavailable">
      <div className="validation-section-header">
        <h4>Validation details</h4>
      </div>
      <p className="empty-state">{message}</p>
    </section>
  );
}

function DashboardWorkspace({
  connection,
  dashboardViewState,
  onRefresh,
  onOpenMachineLoad,
  onOpenValves,
  onOpenRecommendations,
  onOpenBlockers,
}: {
  connection: ConnectionState;
  dashboardViewState: DashboardViewState;
  onRefresh: () => void;
  onOpenMachineLoad: () => void;
  onOpenValves: () => void;
  onOpenRecommendations: () => void;
  onOpenBlockers: () => void;
}) {
  const summary = dashboardViewState.status === "ready" ? dashboardViewState.summary : null;
  const dashboardPlanningRun = dashboardViewState.status === "ready" ? dashboardViewState.planningRun : null;

  return (
    <>
      <section className="workspace" aria-labelledby="dashboard-title">
        <div className="workspace-main">
          <div className="workspace-copy">
            <p className="eyebrow">Home dashboard</p>
            <h2 id="dashboard-title">Start with the plan summary, then move to the part of the system that needs attention first.</h2>
            <p className="workspace-intro">
              This is the morning control panel: check throughput gap, overloads, blockers, assembly risk, and subcontract pressure without wading through every detail screen first.
            </p>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={dashboardViewState.status === "loading" || connection.status !== "connected"}
              onClick={onRefresh}
              type="button"
            >
              {dashboardViewState.status === "loading" ? "Loading dashboard..." : "Refresh dashboard"}
            </button>
          </div>

          {connection.status === "unavailable" ? (
            <p className="feedback-banner error">Backend unavailable. Start the API and refresh.</p>
          ) : null}

          {dashboardViewState.status === "loading" ? (
            <div aria-live="polite" className="progress-band" role="status">
              <span>Loading latest calculated planning run and home dashboard...</span>
              <div aria-hidden="true" className="progress-track">
                <div className="progress-indicator" />
              </div>
            </div>
          ) : null}

          {dashboardViewState.status === "error" ? (
            <p className="feedback-banner error">{dashboardViewState.message}</p>
          ) : null}

          {dashboardViewState.status === "empty" ? (
            <p className="feedback-banner warning">{dashboardViewState.message}</p>
          ) : null}
        </div>

        <aside className="workspace-side" aria-label="Dashboard status">
          <StatusStack
            items={[
              {
                label: "Backend",
                value:
                  connection.status === "connected"
                    ? `${connection.health.environment} ready`
                    : connection.status === "checking"
                      ? "Checking"
                      : "Unavailable",
              },
              {
                label: "Planning run",
                value:
                  dashboardViewState.status === "ready"
                    ? dashboardViewState.planningRun.id
                    : dashboardViewState.status === "loading"
                      ? "Loading latest calculated run"
                      : "No calculated run loaded",
              },
              {
                label: "Triage priority",
                value:
                  summary === null
                    ? "Waiting on dashboard"
                    : summary.flow_blockers > 0
                      ? "Flow blockers first"
                      : summary.assembly_risk_valves > 0
                        ? "Assembly risk first"
                        : summary.overloaded_machines > 0
                          ? "Machine overload first"
                          : "Throughput and balancing",
              },
            ]}
          />

          {dashboardViewState.status === "ready" ? (
            <div className="side-summary">
              <h3>Latest calculated run</h3>
              <dl className="summary-grid">
                <div>
                  <dt>Planning start</dt>
                  <dd>{dashboardViewState.planningRun.planning_start_date}</dd>
                </div>
                <div>
                  <dt>Horizon</dt>
                  <dd>{dashboardViewState.planningRun.planning_horizon_days} days</dd>
                </div>
                <div>
                  <dt>Calculated at</dt>
                  <dd>{dashboardViewState.planningRun.calculated_at ?? "-"}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="side-note">
              <h3>What this screen answers</h3>
              <ul>
                <li>What needs attention first.</li>
                <li>Where the week is at risk.</li>
                <li>Which detailed screen to open next.</li>
              </ul>
            </div>
          )}
        </aside>
      </section>

      {summary !== null ? (
        <section className="validation-layout" aria-labelledby="dashboard-results-title">
          <div className="validation-header">
            <p className="eyebrow">Plan triage</p>
            <h3 id="dashboard-results-title">Use the top-line numbers to choose the next detailed review instead of treating every issue as equally urgent.</h3>
          </div>

          <section aria-label="Dashboard summary" className="validation-section">
            <div className="validation-section-header">
              <h4>Home dashboard summary</h4>
              <span>{dashboardPlanningRun?.planning_horizon_days ?? "-"} days</span>
            </div>

            <div className="metric-grid">
              <div className="metric-card">
                <span>Active valves</span>
                <strong>{summary.active_valves}</strong>
              </div>
              <div className="metric-card">
                <span>Active value</span>
                <strong>{formatDecimal(summary.active_value_cr)} Cr</strong>
              </div>
              <div className="metric-card">
                <span>Planned throughput</span>
                <strong>{formatDecimal(summary.planned_throughput_value_cr)} Cr</strong>
              </div>
              <div className="metric-card">
                <span>Throughput gap</span>
                <strong>{formatDecimal(summary.throughput_gap_cr)} Cr</strong>
              </div>
              <div className="metric-card">
                <span>Overloaded machines</span>
                <strong>{summary.overloaded_machines}</strong>
              </div>
              <div className="metric-card">
                <span>Underutilized machines</span>
                <strong>{summary.underutilized_machines}</strong>
              </div>
              <div className="metric-card">
                <span>Flow blockers</span>
                <strong>{summary.flow_blockers}</strong>
              </div>
              <div className="metric-card">
                <span>Assembly risk valves</span>
                <strong>{summary.assembly_risk_valves}</strong>
              </div>
              <div className="metric-card">
                <span>Subcontract recommendations</span>
                <strong>{summary.subcontract_recommendations}</strong>
              </div>
              <div className="metric-card">
                <span>Batch risks</span>
                <strong>{summary.batch_risks}</strong>
              </div>
            </div>
          </section>

          <section aria-label="Dashboard actions" className="validation-section">
            <div className="validation-section-header">
              <h4>Open the next review</h4>
              <span>Triage</span>
            </div>

            <div className="action-row">
              <button className="secondary-button" onClick={onOpenBlockers} type="button">
                Open flow blockers
              </button>
              <button className="secondary-button" onClick={onOpenMachineLoad} type="button">
                Open machine load
              </button>
              <button className="secondary-button" onClick={onOpenValves} type="button">
                Open valves
              </button>
              <button className="secondary-button" onClick={onOpenRecommendations} type="button">
                Open recommendations
              </button>
            </div>
          </section>
        </section>
      ) : null}
    </>
  );
}

function BlockerWorkspace({
  connection,
  blockerViewState,
  onRefresh,
}: {
  connection: ConnectionState;
  blockerViewState: BlockerViewState;
  onRefresh: () => void;
}) {
  const blockers = blockerViewState.status === "ready" ? sortFlowBlockers(blockerViewState.blockers) : [];
  const groupedBlockers =
    blockerViewState.status === "ready"
      ? BLOCKER_TYPE_ORDER
          .map((blockerType) => ({
            blockerType,
            items: blockers.filter((row) => row.blocker_type === blockerType),
          }))
          .filter((group) => group.items.length > 0)
      : [];
  const criticalCount = blockers.filter((row) => row.severity === "CRITICAL").length;
  const warningCount = blockers.filter((row) => row.severity === "WARNING").length;
  const infoCount = blockers.filter((row) => row.severity === "INFO").length;

  return (
    <>
      <section className="workspace" aria-labelledby="blockers-title">
        <div className="workspace-main">
          <div className="workspace-copy">
            <p className="eyebrow">Flow blockers</p>
            <h2 id="blockers-title">Group the blockers by type, then decide which ones need action before the plan can move cleanly.</h2>
            <p className="workspace-intro">
              Start with critical blockers, then work down through warnings and informational issues. Each row should tell you what is wrong, where it lives, and what to do next.
            </p>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={blockerViewState.status === "loading" || connection.status !== "connected"}
              onClick={onRefresh}
              type="button"
            >
              {blockerViewState.status === "loading" ? "Loading blockers..." : "Refresh blockers"}
            </button>
          </div>

          {connection.status === "unavailable" ? (
            <p className="feedback-banner error">Backend unavailable. Start the API and refresh.</p>
          ) : null}

          {blockerViewState.status === "loading" ? (
            <div aria-live="polite" className="progress-band" role="status">
              <span>Loading latest calculated planning run and flow blockers...</span>
              <div aria-hidden="true" className="progress-track">
                <div className="progress-indicator" />
              </div>
            </div>
          ) : null}

          {blockerViewState.status === "error" ? <p className="feedback-banner error">{blockerViewState.message}</p> : null}
          {blockerViewState.status === "empty" ? <p className="feedback-banner warning">{blockerViewState.message}</p> : null}
        </div>

        <aside className="workspace-side" aria-label="Blocker status">
          <StatusStack
            items={[
              {
                label: "Backend",
                value:
                  connection.status === "connected"
                    ? `${connection.health.environment} ready`
                    : connection.status === "checking"
                      ? "Checking"
                      : "Unavailable",
              },
              {
                label: "Planning run",
                value:
                  blockerViewState.status === "ready"
                    ? blockerViewState.planningRun.id
                    : blockerViewState.status === "loading"
                      ? "Loading latest calculated run"
                      : "No calculated run loaded",
              },
              {
                label: "Severity focus",
                value:
                  blockerViewState.status !== "ready"
                    ? "Waiting on blockers"
                    : criticalCount > 0
                      ? "Critical first"
                      : warningCount > 0
                        ? "Warnings next"
                        : "Informational review",
              },
            ]}
          />

          {blockerViewState.status === "ready" ? (
            <div className="side-summary">
              <h3>Blocker counts</h3>
              <dl className="summary-grid">
                <div>
                  <dt>Critical</dt>
                  <dd>{criticalCount}</dd>
                </div>
                <div>
                  <dt>Warning</dt>
                  <dd>{warningCount}</dd>
                </div>
                <div>
                  <dt>Info</dt>
                  <dd>{infoCount}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="side-note">
              <h3>What this screen answers</h3>
              <ul>
                <li>Which blocker types are active right now.</li>
                <li>Which valves and operations are affected.</li>
                <li>What action the planner should take next.</li>
              </ul>
            </div>
          )}
        </aside>
      </section>

      {blockerViewState.status === "ready" ? (
        <section className="validation-layout" aria-labelledby="blockers-results-title">
          <div className="validation-header">
            <p className="eyebrow">Grouped blocker review</p>
            <h3 id="blockers-results-title">Work blocker type by blocker type so data problems, overloads, and vendor issues stay distinct.</h3>
          </div>

          {groupedBlockers.map((group) => (
            <section aria-label={`${group.blockerType} blockers`} className="validation-section" key={group.blockerType}>
              <div className="validation-section-header">
                <h4>{group.blockerType}</h4>
                <span>{group.items.length}</span>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Severity</th>
                      <th>Valve</th>
                      <th>Component</th>
                      <th>Operation</th>
                      <th>Cause</th>
                      <th>Recommended action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <span className={`status-pill status-${row.severity.toLowerCase()}`}>{row.severity}</span>
                        </td>
                        <td>{row.valve_id ?? "-"}</td>
                        <td>{row.component ?? "-"}</td>
                        <td>{row.operation_name ?? "-"}</td>
                        <td>{row.cause}</td>
                        <td>{row.recommended_action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </section>
      ) : null}
    </>
  );
}

function ValidationSection({
  title,
  issues,
  emptyMessage,
}: {
  title: string;
  issues: ValidationIssueResponse[];
  emptyMessage: string;
}) {
  return (
    <section aria-label={title} className="validation-section">
      <div className="validation-section-header">
        <h4>{title}</h4>
        <span>{issues.length}</span>
      </div>

      {issues.length === 0 ? (
        <p className="empty-state">{emptyMessage}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Severity</th>
                <th>Sheet</th>
                <th>Row</th>
                <th>Field</th>
                <th>Issue</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {issues.map((issue) => (
                <tr key={issue.id}>
                  <td>{issue.severity}</td>
                  <td>{issue.sheet_name ?? "-"}</td>
                  <td>{issue.row_number ?? "-"}</td>
                  <td>{issue.field_name ?? "-"}</td>
                  <td>{issue.message}</td>
                  <td>{recommendedAction(issue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function recommendedAction(issue: ValidationIssueResponse) {
  if (issue.severity === "BLOCKING") {
    return issue.field_name
      ? `Fix ${issue.field_name} in Excel and upload again.`
      : "Fix the source row in Excel and upload again.";
  }

  return "Review before planning run.";
}

function ConnectionBadge({ connection }: { connection: ConnectionState }) {
  if (connection.status === "connected") {
    return (
      <div className="connection connected" role="status">
        <span>Connected</span>
        <small>{connection.health.environment}</small>
      </div>
    );
  }

  if (connection.status === "unavailable") {
    return (
      <div className="connection unavailable" role="status">
        <span>Backend unavailable</span>
        <small>Start the API and refresh</small>
      </div>
    );
  }

  return (
    <div className="connection checking" role="status">
      <span>Checking backend</span>
      <small>Please wait</small>
    </div>
  );
}

function StatusStack({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="status-strip" aria-label="Foundation status">
      {items.map((item) => (
        <div className="status-item" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function MachineLoadWorkspace({
  connection,
  machineLoadViewState,
  onRefresh,
  onOpenQueue,
}: {
  connection: ConnectionState;
  machineLoadViewState: MachineLoadViewState;
  onRefresh: () => void;
  onOpenQueue: (machineType: string) => void;
}) {
  const machineLoadItems = machineLoadViewState.status === "ready" ? machineLoadViewState.machineLoad : [];
  const queueState = machineLoadViewState.status === "ready" ? machineLoadViewState.queue : { status: "idle" as const };
  const selectedMachineType = machineLoadViewState.status === "ready" ? machineLoadViewState.selectedMachineType : null;
  const selectedQueueLabel =
    queueState.status === "loading" || queueState.status === "error"
      ? queueState.machineType
      : queueState.status === "ready"
        ? queueState.data.machine_type
        : selectedMachineType ?? "No machine selected";

  return (
    <>
      <section className="workspace" aria-labelledby="machine-load-title">
        <div className="workspace-main">
          <div className="workspace-copy">
            <p className="eyebrow">Machine load</p>
            <h2 id="machine-load-title">See which machine types are carrying the week and what is sitting in queue.</h2>
            <p className="workspace-intro">
              Start from the latest calculated planning run, scan capacity pressure by machine type, then open the queue
              to understand exactly which operations are consuming the load.
            </p>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={machineLoadViewState.status === "loading" || connection.status !== "connected"}
              onClick={onRefresh}
              type="button"
            >
              {machineLoadViewState.status === "loading" ? "Loading machine load..." : "Refresh machine load"}
            </button>
          </div>

          {connection.status === "unavailable" ? (
            <p className="feedback-banner error">Backend unavailable. Start the API and refresh.</p>
          ) : null}

          {machineLoadViewState.status === "loading" ? (
            <div aria-live="polite" className="progress-band" role="status">
              <span>Loading latest calculated planning run and machine queue...</span>
              <div aria-hidden="true" className="progress-track">
                <div className="progress-indicator" />
              </div>
            </div>
          ) : null}

          {machineLoadViewState.status === "error" ? (
            <p className="feedback-banner error">{machineLoadViewState.message}</p>
          ) : null}

          {machineLoadViewState.status === "empty" ? (
            <p className="feedback-banner warning">{machineLoadViewState.message}</p>
          ) : null}
        </div>

        <aside className="workspace-side" aria-label="Machine load status">
          <StatusStack
            items={[
              {
                label: "Backend",
                value:
                  connection.status === "connected"
                    ? `${connection.health.environment} ready`
                    : connection.status === "checking"
                      ? "Checking"
                      : "Unavailable",
              },
              {
                label: "Planning run",
                value:
                  machineLoadViewState.status === "ready"
                    ? machineLoadViewState.planningRun.id
                    : machineLoadViewState.status === "loading"
                      ? "Loading latest calculated run"
                      : "No calculated run loaded",
              },
              {
                label: "Queue",
                value: selectedQueueLabel,
              },
            ]}
          />

          {machineLoadViewState.status === "ready" ? (
            <div className="side-summary">
              <h3>Latest calculated run</h3>
              <dl className="summary-grid">
                <div>
                  <dt>Planning start</dt>
                  <dd>{machineLoadViewState.planningRun.planning_start_date}</dd>
                </div>
                <div>
                  <dt>Horizon</dt>
                  <dd>{machineLoadViewState.planningRun.planning_horizon_days} days</dd>
                </div>
                <div>
                  <dt>Calculated at</dt>
                  <dd>{machineLoadViewState.planningRun.calculated_at ?? "-"}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="side-note">
              <h3>What this screen answers</h3>
              <ul>
                <li>Which machine types are overloaded or underutilized.</li>
                <li>How many days of load sit against each machine buffer.</li>
                <li>Which operations are actually consuming the queue.</li>
              </ul>
            </div>
          )}
        </aside>
      </section>

      {machineLoadViewState.status === "ready" ? (
        <section className="validation-layout" aria-labelledby="machine-load-results-title">
          <div className="validation-header">
            <p className="eyebrow">Capacity review</p>
            <h3 id="machine-load-results-title">Open a machine type to inspect its queue before making a move.</h3>
          </div>

          <section aria-label="Machine load table" className="validation-section">
            <div className="validation-section-header">
              <h4>Machine load</h4>
              <span>{machineLoadItems.length}</span>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Machine</th>
                    <th>Total hours</th>
                    <th>Capacity/day</th>
                    <th>Load days</th>
                    <th>Buffer days</th>
                    <th>Overload</th>
                    <th>Spare capacity</th>
                    <th>Underutilized</th>
                    <th>Batch risk</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {machineLoadItems.map((row) => (
                    <tr
                      className={row.machine_type === selectedMachineType ? "selected-row" : undefined}
                      key={row.machine_type}
                    >
                      <td>
                        <button
                          className="table-button"
                          onClick={() => onOpenQueue(row.machine_type)}
                          type="button"
                        >
                          Open {row.machine_type} queue
                        </button>
                      </td>
                      <td>{formatDecimal(row.total_operation_hours)}</td>
                      <td>{formatDecimal(row.capacity_hours_per_day)}</td>
                      <td>{formatDecimal(row.load_days)}</td>
                      <td>{formatDecimal(row.buffer_days)}</td>
                      <td>{row.overload_flag ? formatDecimal(row.overload_days) : "0.00"}</td>
                      <td>{formatDecimal(row.spare_capacity_days)}</td>
                      <td>{row.underutilized_flag ? "Yes" : "No"}</td>
                      <td>{row.batch_risk_flag ? "Yes" : "No"}</td>
                      <td>
                        <span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-label="Machine queue detail" className="validation-section">
            <div className="validation-section-header">
              <h4>{selectedMachineType ? `${selectedMachineType} queue detail` : "Queue detail"}</h4>
              <span>
                {queueState.status === "ready"
                  ? queueState.data.total
                  : queueState.status === "loading"
                    ? "Loading"
                    : queueState.status === "error"
                      ? "Retry needed"
                      : "0"}
              </span>
            </div>

            {queueState.status === "loading" ? (
              <div aria-live="polite" className="progress-band" role="status">
                <span>Loading queue detail...</span>
                <div aria-hidden="true" className="progress-track">
                  <div className="progress-indicator" />
                </div>
              </div>
            ) : null}

            {queueState.status === "error" ? <p className="feedback-banner error">{queueState.message}</p> : null}

            {queueState.status === "ready" ? (
              <>
                {queueState.data.queue_approximation_warning ? (
                  <p className="feedback-banner warning">{queueState.data.queue_approximation_warning}</p>
                ) : null}
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Sequence</th>
                        <th>Priority score</th>
                        <th>Valve</th>
                        <th>Component</th>
                        <th>Operation</th>
                        <th>Availability date</th>
                        <th>Date confidence</th>
                        <th>Operation hours</th>
                        <th>Internal wait days</th>
                        <th>Processing days</th>
                        <th>Completion date</th>
                        <th>Recommendation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {queueState.data.items.map((row) => (
                        <tr key={row.id}>
                          <td>{row.sort_sequence}</td>
                          <td>{formatDecimal(row.priority_score)}</td>
                          <td>{row.valve_id}</td>
                          <td>{row.component}</td>
                          <td>{row.operation_name}</td>
                          <td>{row.availability_date}</td>
                          <td>{row.date_confidence}</td>
                          <td>{formatDecimal(row.operation_hours)}</td>
                          <td>{formatNullableDecimal(row.internal_wait_days)}</td>
                          <td>{formatNullableDecimal(row.processing_time_days)}</td>
                          <td>{row.internal_completion_date ?? "-"}</td>
                          <td>{row.recommendation_status ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </section>
        </section>
      ) : null}
    </>
  );
}

function ValveWorkspace({
  connection,
  valveViewState,
  onRefresh,
  onOpenComponentStatus,
}: {
  connection: ConnectionState;
  valveViewState: ValveViewState;
  onRefresh: () => void;
  onOpenComponentStatus: (valveId: string) => void;
}) {
  const readinessItems = valveViewState.status === "ready" ? valveViewState.valveReadiness : [];
  const assemblyRiskItems = valveViewState.status === "ready" ? valveViewState.assemblyRisk : [];
  const assemblyRiskMessage = valveViewState.status === "ready" ? valveViewState.assemblyRiskMessage : null;
  const componentStatusState =
      valveViewState.status === "ready" ? valveViewState.componentStatus : ({ status: "idle" } as const);
  const selectedValveId = valveViewState.status === "ready" ? valveViewState.selectedValveId : null;
  const selectedComponentValveLabel =
    componentStatusState.status === "loading" || componentStatusState.status === "error"
      ? componentStatusState.valveId
      : componentStatusState.status === "ready"
        ? componentStatusState.data.valve_id
        : selectedValveId ?? "No valve selected";

  return (
    <>
      <section className="workspace" aria-labelledby="valves-title">
        <div className="workspace-main">
          <div className="workspace-copy">
            <p className="eyebrow">Valves and assembly risk</p>
            <h2 id="valves-title">See which valves are truly ready, what is blocking each one, and where assembly risk is building.</h2>
            <p className="workspace-intro">
              Start from the latest calculated planning run, review valve readiness, open one valve at a time to see
              component-level blockers, and use assembly risk as the management view of who may miss the assembly date.
            </p>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={valveViewState.status === "loading" || connection.status !== "connected"}
              onClick={onRefresh}
              type="button"
            >
              {valveViewState.status === "loading" ? "Loading valve readiness..." : "Refresh valves"}
            </button>
          </div>

          {connection.status === "unavailable" ? (
            <p className="feedback-banner error">Backend unavailable. Start the API and refresh.</p>
          ) : null}

          {valveViewState.status === "loading" ? (
            <div aria-live="polite" className="progress-band" role="status">
              <span>Loading latest calculated planning run, valve readiness, and assembly risk...</span>
              <div aria-hidden="true" className="progress-track">
                <div className="progress-indicator" />
              </div>
            </div>
          ) : null}

          {valveViewState.status === "error" ? <p className="feedback-banner error">{valveViewState.message}</p> : null}

          {valveViewState.status === "empty" ? <p className="feedback-banner warning">{valveViewState.message}</p> : null}
        </div>

        <aside className="workspace-side" aria-label="Valve status">
          <StatusStack
            items={[
              {
                label: "Backend",
                value:
                  connection.status === "connected"
                    ? `${connection.health.environment} ready`
                    : connection.status === "checking"
                      ? "Checking"
                      : "Unavailable",
              },
              {
                label: "Planning run",
                value:
                  valveViewState.status === "ready"
                    ? valveViewState.planningRun.id
                    : valveViewState.status === "loading"
                      ? "Loading latest calculated run"
                      : "No calculated run loaded",
              },
              {
                label: "Valve detail",
                value: selectedComponentValveLabel,
              },
            ]}
          />

          {valveViewState.status === "ready" ? (
            <div className="side-summary">
              <h3>Latest calculated run</h3>
              <dl className="summary-grid">
                <div>
                  <dt>Planning start</dt>
                  <dd>{valveViewState.planningRun.planning_start_date}</dd>
                </div>
                <div>
                  <dt>Horizon</dt>
                  <dd>{valveViewState.planningRun.planning_horizon_days} days</dd>
                </div>
                  <div>
                    <dt>Assembly risk</dt>
                    <dd>{assemblyRiskMessage ? "Retry needed" : `${assemblyRiskItems.length} valves`}</dd>
                  </div>
                </dl>
              </div>
          ) : (
            <div className="side-note">
              <h3>What this screen answers</h3>
              <ul>
                <li>Which valves are ready, near ready, not ready, or at risk.</li>
                <li>What exactly is blocking a selected valve at component level.</li>
                <li>Which valves may miss assembly date and why.</li>
              </ul>
            </div>
          )}
        </aside>
      </section>

      {valveViewState.status === "ready" ? (
        <section className="validation-layout" aria-labelledby="valves-results-title">
          <div className="validation-header">
            <p className="eyebrow">Readiness and risk</p>
            <h3 id="valves-results-title">Open a valve to inspect component status, then use assembly risk to decide where to intervene first.</h3>
          </div>

          <section aria-label="Valve readiness table" className="validation-section">
            <div className="validation-section-header">
              <h4>Valve readiness</h4>
              <span>{readinessItems.length}</span>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Valve</th>
                    <th>Customer</th>
                    <th>Assembly date</th>
                    <th>Dispatch date</th>
                    <th>Total components</th>
                    <th>Ready components</th>
                    <th>Critical ready</th>
                    <th>Status</th>
                    <th>Expected completion</th>
                    <th>Assembly delay days</th>
                    <th>Risk reason</th>
                  </tr>
                </thead>
                <tbody>
                  {readinessItems.map((row) => (
                    <tr className={row.valve_id === selectedValveId ? "selected-row" : undefined} key={row.valve_id}>
                      <td>
                        <button
                          className="table-button"
                          onClick={() => onOpenComponentStatus(row.valve_id)}
                          type="button"
                        >
                          Open {row.valve_id}
                        </button>
                      </td>
                      <td>{row.customer}</td>
                      <td>{row.assembly_date}</td>
                      <td>{row.dispatch_date}</td>
                      <td>{row.total_components}</td>
                      <td>{row.ready_components}</td>
                      <td>
                        {row.ready_required_count}/{row.required_components}
                      </td>
                      <td>
                        <span className={`status-pill status-${row.readiness_status.toLowerCase()}`}>{row.readiness_status}</span>
                      </td>
                      <td>{row.valve_expected_completion_date ?? "-"}</td>
                      <td>{formatDecimal(row.otd_delay_days)}</td>
                      <td>{row.risk_reason ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-label="Component status detail" className="validation-section">
            <div className="validation-section-header">
              <h4>{selectedValveId ? `${selectedValveId} component status` : "Component status"}</h4>
              <span>
                {componentStatusState.status === "ready"
                  ? componentStatusState.data.total
                  : componentStatusState.status === "loading"
                    ? "Loading"
                    : componentStatusState.status === "error"
                      ? "Retry needed"
                      : "0"}
              </span>
            </div>

            {componentStatusState.status === "loading" ? (
              <div aria-live="polite" className="progress-band" role="status">
                <span>Loading component status...</span>
                <div aria-hidden="true" className="progress-track">
                  <div className="progress-indicator" />
                </div>
              </div>
            ) : null}

            {componentStatusState.status === "error" ? (
              <p className="feedback-banner error">{componentStatusState.message}</p>
            ) : null}

            {componentStatusState.status === "ready" ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Component line</th>
                      <th>Component</th>
                      <th>Current location</th>
                      <th>Fabrication complete</th>
                      <th>Critical</th>
                      <th>Availability date</th>
                      <th>Date confidence</th>
                      <th>Next operation</th>
                      <th>Internal wait days</th>
                      <th>Status</th>
                      <th>Blockers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {componentStatusState.data.items.map((row) => (
                      <tr key={`${row.valve_id}-${row.component_line_no}`}>
                        <td>{row.component_line_no}</td>
                        <td>{row.component}</td>
                        <td>{row.current_location ?? "-"}</td>
                        <td>{row.fabrication_complete ? "Yes" : "No"}</td>
                        <td>{row.critical ? "Yes" : "No"}</td>
                        <td>{row.availability_date}</td>
                        <td>
                          <span className={`confidence-pill confidence-${row.date_confidence.toLowerCase()}`}>{row.date_confidence}</span>
                        </td>
                        <td>
                          {row.next_operation_name
                            ? `${row.next_operation_name}${row.next_machine_type ? ` (${row.next_machine_type})` : ""}`
                            : "-"}
                        </td>
                        <td>{formatNullableDecimal(row.internal_wait_days)}</td>
                        <td>
                          <span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status}</span>
                        </td>
                        <td>{row.blocker_summary ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>

            <section aria-label="Assembly risk table" className="validation-section">
              <div className="validation-section-header">
                <h4>Assembly risk</h4>
                <span>{assemblyRiskMessage ? "Retry needed" : assemblyRiskItems.length}</span>
              </div>

              {assemblyRiskMessage ? (
                <p className="feedback-banner warning">{assemblyRiskMessage}</p>
              ) : null}

              {assemblyRiskMessage ? null : assemblyRiskItems.length === 0 ? (
                <p className="empty-state">No valves are currently flagged at assembly risk.</p>
              ) : (
                <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Valve</th>
                      <th>Customer</th>
                      <th>Assembly date</th>
                      <th>Expected completion date</th>
                      <th>Assembly delay days</th>
                      <th>Reason</th>
                      <th>Suggested action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assemblyRiskItems.map((row) => (
                      <tr key={row.valve_id}>
                        <td>
                          <button
                            className="table-button"
                            onClick={() => onOpenComponentStatus(row.valve_id)}
                            type="button"
                          >
                            Open {row.valve_id}
                          </button>
                        </td>
                        <td>{row.customer}</td>
                        <td>{row.assembly_date}</td>
                        <td>{row.expected_completion_date ?? "-"}</td>
                        <td>{formatDecimal(row.assembly_delay_days)}</td>
                        <td>{row.reason ?? "-"}</td>
                        <td>{row.suggested_action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </section>
      ) : null}
    </>
  );
}

function RecommendationWorkspace({
  connection,
  recommendationViewState,
  recommendationActionDraft,
  recommendationActionMessage,
  isSubmittingRecommendationAction,
  onRefresh,
  onStartAction,
  onActionDraftChange,
  onCancelAction,
  onSubmitAction,
}: {
  connection: ConnectionState;
  recommendationViewState: RecommendationViewState;
  recommendationActionDraft: RecommendationActionDraft | null;
  recommendationActionMessage: string | null;
  isSubmittingRecommendationAction: boolean;
  onRefresh: () => void;
  onStartAction: (
    recommendationId: string,
    decisionMode: RecommendationActionDraft["decisionMode"],
  ) => void;
  onActionDraftChange: (draft: RecommendationActionDraft | null) => void;
  onCancelAction: () => void;
  onSubmitAction: () => void;
}) {
  const recommendations = recommendationViewState.status === "ready" ? recommendationViewState.recommendations : [];
  const vendorLoad = recommendationViewState.status === "ready" ? recommendationViewState.vendorLoad : [];
  const vendorLoadMessage = recommendationViewState.status === "ready" ? recommendationViewState.vendorLoadMessage : null;
  const actionLog = recommendationViewState.status === "ready" ? recommendationViewState.actionLog : [];
  const actionLogMessage = recommendationViewState.status === "ready" ? recommendationViewState.actionLogMessage : null;
  const selectedRecommendation =
    recommendationViewState.status === "ready" && recommendationActionDraft !== null
      ? recommendationViewState.recommendations.find((row) => row.id === recommendationActionDraft.recommendationId) ?? null
      : null;

  return (
    <>
      <section className="workspace" aria-labelledby="recommendations-title">
        <div className="workspace-main">
          <div className="workspace-copy">
            <p className="eyebrow">Recommendations and decisions</p>
            <h2 id="recommendations-title">Review subcontract and no-feasible-option calls, decide with a reason, and keep the audit trail visible.</h2>
            <p className="workspace-intro">
              Work from the latest calculated planning run, review subcontract and no-feasible-option calls with the numbers attached, save planner decisions with a reason, and keep vendor exposure plus the action log in the same conversation.
            </p>
          </div>

          <div className="action-row">
            <button
              className="primary-button"
              disabled={
                recommendationViewState.status === "loading" ||
                connection.status !== "connected" ||
                isSubmittingRecommendationAction
              }
              onClick={onRefresh}
              type="button"
            >
              {recommendationViewState.status === "loading" ? "Loading recommendations..." : "Refresh recommendations"}
            </button>
          </div>

          {connection.status === "unavailable" ? (
            <p className="feedback-banner error">Backend unavailable. Start the API and refresh.</p>
          ) : null}

          {recommendationViewState.status === "loading" ? (
            <div aria-live="polite" className="progress-band" role="status">
              <span>Loading latest calculated planning run, recommendations, vendor exposure, and action log...</span>
              <div aria-hidden="true" className="progress-track">
                <div className="progress-indicator" />
              </div>
            </div>
          ) : null}

          {recommendationViewState.status === "error" ? (
            <p className="feedback-banner error">{recommendationViewState.message}</p>
          ) : null}

          {recommendationViewState.status === "empty" ? (
            <p className="feedback-banner warning">{recommendationViewState.message}</p>
          ) : null}
        </div>

        <aside className="workspace-side" aria-label="Recommendation status">
          <StatusStack
            items={[
              {
                label: "Backend",
                value:
                  connection.status === "connected"
                    ? `${connection.health.environment} ready`
                    : connection.status === "checking"
                      ? "Checking"
                      : "Unavailable",
              },
              {
                label: "Planning run",
                value:
                  recommendationViewState.status === "ready"
                    ? recommendationViewState.planningRun.id
                    : recommendationViewState.status === "loading"
                      ? "Loading latest calculated run"
                      : "No calculated run loaded",
              },
              {
                label: "Decision draft",
                value:
                  recommendationActionDraft === null
                    ? "No action in progress"
                    : recommendationActionDraft.decisionMode === "OVERRIDE"
                      ? recommendationActionDraft.overrideChoice
                      : recommendationActionDraft.decisionMode,
              },
            ]}
          />

          {recommendationViewState.status === "ready" ? (
            <div className="side-summary">
              <h3>Recommendation snapshot</h3>
              <dl className="summary-grid">
                <div>
                  <dt>Planning start</dt>
                  <dd>{recommendationViewState.planningRun.planning_start_date}</dd>
                </div>
                <div>
                  <dt>Horizon</dt>
                  <dd>{recommendationViewState.planningRun.planning_horizon_days} days</dd>
                </div>
                <div>
                  <dt>Recommendations</dt>
                  <dd>{recommendations.length}</dd>
                </div>
                <div>
                  <dt>Action log</dt>
                  <dd>{actionLogMessage ? "Retry needed" : actionLog.length}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <div className="side-note">
              <h3>What this screen answers</h3>
              <ul>
                <li>Which operations should go to vendor or stay in-house for now.</li>
                <li>What numbers justify each subcontract-facing recommendation.</li>
                <li>Which vendor limits and planner decisions need review.</li>
              </ul>
            </div>
          )}
        </aside>
      </section>

      {recommendationViewState.status === "ready" ? (
        <section className="validation-layout" aria-labelledby="recommendation-results-title">
          <div className="validation-header">
            <p className="eyebrow">Recommendations and audit</p>
            <h3 id="recommendation-results-title">Decide one recommendation at a time, keep the numbers visible, and leave an audit trail behind every planner action.</h3>
          </div>

          <section aria-label="Recommendation table" className="validation-section">
            <div className="validation-section-header">
              <h4>Subcontract recommendations</h4>
              <span>{recommendations.length}</span>
            </div>

            {recommendations.length === 0 ? (
              <p className="empty-state">No subcontract recommendations. Internal plan is within current subcontract rules.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Valve</th>
                      <th>Component</th>
                      <th>Operation</th>
                      <th>Machine</th>
                      <th>Recommendation</th>
                      <th>Suggested vendor</th>
                      <th>Internal wait days</th>
                      <th>Internal completion days</th>
                      <th>Vendor total days</th>
                      <th>Vendor gain days</th>
                      <th>Status</th>
                      <th>Explanation</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map((row) => (
                      <tr
                        className={recommendationActionDraft?.recommendationId === row.id ? "selected-row" : undefined}
                        key={row.id}
                      >
                        <td>{row.valve_id ?? "-"}</td>
                        <td>{row.component ?? "-"}</td>
                        <td>{row.operation_name ?? "-"}</td>
                        <td>{row.machine_type ?? "-"}</td>
                        <td>{row.recommendation_type}</td>
                        <td>{row.suggested_vendor_name ?? row.suggested_vendor_id ?? row.suggested_machine_type ?? "-"}</td>
                        <td>{formatNullableDecimal(row.internal_wait_days)}</td>
                        <td>{formatNullableDecimal(row.internal_completion_days)}</td>
                        <td>{formatNullableDecimal(row.vendor_total_days)}</td>
                        <td>{formatNullableDecimal(row.vendor_gain_days)}</td>
                        <td>
                          <span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status}</span>
                        </td>
                        <td>{row.explanation}</td>
                        <td>
                          <div className="table-actions">
                            <button
                              className="table-button"
                              disabled={isSubmittingRecommendationAction}
                              onClick={() => onStartAction(row.id, "ACCEPT")}
                              type="button"
                            >
                              Accept
                            </button>
                            <button
                              className="table-button"
                              disabled={isSubmittingRecommendationAction}
                              onClick={() => onStartAction(row.id, "REJECT")}
                              type="button"
                            >
                              Reject
                            </button>
                            <button
                              className="table-button"
                              disabled={isSubmittingRecommendationAction}
                              onClick={() => onStartAction(row.id, "OVERRIDE")}
                              type="button"
                            >
                              Override
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {recommendationActionDraft !== null && selectedRecommendation !== null ? (
              <div className="action-form">
                <div className="validation-section-header">
                  <h4>Decision for {selectedRecommendation.valve_id ?? "selected valve"} / {selectedRecommendation.component ?? "selected component"}</h4>
                  <span>{selectedRecommendation.recommendation_type}</span>
                </div>
                <p className="empty-state">
                  Recommendation: {selectedRecommendation.explanation}
                </p>
                <div className="action-form-grid">
                  <label className="field-label">
                    Decision
                    <input
                      className="text-input"
                      disabled
                      type="text"
                      value={
                        recommendationActionDraft.decisionMode === "OVERRIDE"
                          ? "OVERRIDE"
                          : recommendationActionDraft.decisionMode
                      }
                    />
                  </label>

                  {recommendationActionDraft.decisionMode === "OVERRIDE" ? (
                    <label className="field-label">
                      Override choice
                      <select
                        className="text-input"
                        onChange={(event) =>
                          onActionDraftChange({
                            ...recommendationActionDraft,
                            overrideChoice: event.target.value as RecommendationActionDraft["overrideChoice"],
                          })
                        }
                        value={recommendationActionDraft.overrideChoice}
                      >
                        <option value="FORCE_IN_HOUSE">Force in-house</option>
                        <option value="FORCE_VENDOR">Force vendor</option>
                        <option value="OVERRIDE">Override</option>
                      </select>
                    </label>
                  ) : null}

                  <label className="field-label field-span-2">
                    Decision reason
                    <input
                      className="text-input"
                      onChange={(event) =>
                        onActionDraftChange({
                          ...recommendationActionDraft,
                          reason: event.target.value,
                        })
                      }
                      placeholder="Customer escalation, vendor quality concern, machine setup already planned..."
                      type="text"
                      value={recommendationActionDraft.reason}
                    />
                  </label>

                  <label className="field-label field-span-2">
                    Remarks
                    <textarea
                      className="text-area"
                      onChange={(event) =>
                        onActionDraftChange({
                          ...recommendationActionDraft,
                          remarks: event.target.value,
                        })
                      }
                      rows={3}
                      value={recommendationActionDraft.remarks}
                    />
                  </label>
                </div>

                {recommendationActionMessage ? (
                  <p
                    className={`feedback-banner ${
                      recommendationActionMessage === "Decision recorded." ? "success" : "warning"
                    }`}
                  >
                    {recommendationActionMessage}
                  </p>
                ) : null}

                <div className="action-row">
                  <button
                    className="primary-button"
                    disabled={isSubmittingRecommendationAction}
                    onClick={onSubmitAction}
                    type="button"
                  >
                    {isSubmittingRecommendationAction ? "Saving decision..." : "Save decision"}
                  </button>
                  <button className="secondary-button" disabled={isSubmittingRecommendationAction} onClick={onCancelAction} type="button">
                    Cancel action
                  </button>
                </div>
              </div>
            ) : recommendationActionMessage ? (
              <p className="feedback-banner success">{recommendationActionMessage}</p>
            ) : null}
          </section>

          <section aria-label="Vendor dashboard" className="validation-section">
            <div className="validation-section-header">
              <h4>Vendor dashboard</h4>
              <span>{vendorLoadMessage ? "Retry needed" : vendorLoad.length}</span>
            </div>

            {vendorLoadMessage ? <p className="feedback-banner warning">{vendorLoadMessage}</p> : null}

            {!vendorLoadMessage && vendorLoad.length === 0 ? (
              <p className="empty-state">No vendor exposure is currently modeled for this planning run.</p>
            ) : null}

            {vendorLoad.length > 0 ? (
              <>
                <p className="feedback-banner warning">{vendorLoad[0].limitation_warning}</p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Vendor</th>
                        <th>Process</th>
                        <th>Recommended jobs</th>
                        <th>Capacity limit</th>
                        <th>Status</th>
                        <th>Capacity rating</th>
                        <th>Reliability</th>
                        <th>Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {vendorLoad.map((row) => (
                        <tr key={row.vendor_id}>
                          <td>{row.vendor_name}</td>
                          <td>{row.primary_process}</td>
                          <td>{row.vendor_recommended_jobs}</td>
                          <td>{row.max_recommended_jobs_per_horizon}</td>
                          <td>
                            <span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status}</span>
                          </td>
                          <td>{row.capacity_rating ?? "-"}</td>
                          <td>{row.reliability ?? "-"}</td>
                          <td>{row.comments ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </section>

          <section aria-label="Planner action log" className="validation-section">
            <div className="validation-section-header">
              <h4>Planner action log</h4>
              <span>{actionLogMessage ? "Retry needed" : actionLog.length}</span>
            </div>

            {actionLogMessage ? <p className="feedback-banner warning">{actionLogMessage}</p> : null}

            {!actionLogMessage && actionLog.length === 0 ? (
              <p className="empty-state">No planner decisions recorded for this planning run yet.</p>
            ) : null}

            {actionLog.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Timestamp</th>
                      <th>Entity</th>
                      <th>Recommendation</th>
                      <th>Decision</th>
                      <th>Reason</th>
                      <th>Remarks</th>
                      <th>Stale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {actionLog.map((row) => (
                      <tr key={row.id}>
                        <td>{row.user_display_name}</td>
                        <td>{formatTimestamp(row.created_at)}</td>
                        <td>{`${row.entity_type} ${row.entity_id}`}</td>
                        <td>{row.original_recommendation ?? "-"}</td>
                        <td>{formatDecisionLabel(row.override_decision)}</td>
                        <td>{row.reason}</td>
                        <td>{row.remarks ?? "-"}</td>
                        <td>
                          <span className={`status-pill status-${row.stale_flag ? "warning" : "ready"}`}>
                            {row.stale_flag ? "STALE" : "CURRENT"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        </section>
      ) : null}
    </>
  );
}

const BLOCKER_TYPE_ORDER = [
  "MISSING_COMPONENT",
  "MISSING_ROUTING",
  "MISSING_MACHINE",
  "MACHINE_OVERLOAD",
  "BATCH_RISK",
  "FLOW_GAP",
  "VALVE_FLOW_IMBALANCE",
  "EXTREME_DELAY",
  "VENDOR_UNAVAILABLE",
  "VENDOR_OVERLOADED",
];

function sortFlowBlockers(blockers: FlowBlockerItemResponse[]) {
  const severityRank: Record<string, number> = {
    CRITICAL: 0,
    WARNING: 1,
    INFO: 2,
  };
  const blockerTypeRank = new Map(BLOCKER_TYPE_ORDER.map((value, index) => [value, index]));

  return [...blockers].sort((left, right) => {
    const severityDelta = (severityRank[left.severity] ?? 99) - (severityRank[right.severity] ?? 99);
    if (severityDelta !== 0) {
      return severityDelta;
    }

    const blockerTypeDelta =
      (blockerTypeRank.get(left.blocker_type) ?? 99) - (blockerTypeRank.get(right.blocker_type) ?? 99);
    if (blockerTypeDelta !== 0) {
      return blockerTypeDelta;
    }

    return left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id);
  });
}

function recommendationStatusForOverrideDecision(overrideDecision: string) {
  if (overrideDecision === "ACCEPT") {
    return "ACCEPTED";
  }
  if (overrideDecision === "REJECT") {
    return "REJECTED";
  }
  return "OVERRIDDEN";
}

function formatDecisionLabel(overrideDecision: string) {
  return overrideDecision
    .toLowerCase()
    .split("_")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function formatTimestamp(value: string) {
  return value.replace("T", " ").replace("Z", " UTC");
}

function formatDecimal(value: number) {
  return value.toFixed(2);
}

function formatNullableDecimal(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}

export default App;

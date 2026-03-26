const FORM_CONFIG = {
    planalto: {
        endpoint: "/planalto",
        filename: "planalto_processado.xlsx",
        requiredCount: 2,
        fields: [
            {
                name: "recebimento",
                formKey: "recebimento",
                label: "Arquivo de recebimento",
                hint: "Envie o XLSX de recebimento do Planalto."
            },
            {
                name: "pagamento",
                formKey: "pagamento",
                label: "Arquivo de pagamento",
                hint: "Envie o XLSX de remessa ou pagamento."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo os anexos obrigatorios." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 55, status: "Processando planilhas...", detail: "Conferindo recebimento e pagamento." },
            { delayMs: 2600, progress: 82, status: "Montando consolidado...", detail: "Aplicando as regras do fluxo Planalto." },
            { delayMs: 4200, progress: 92, status: "Gerando arquivo final...", detail: "Preparando o relatorio para download." }
        ]
    },
    sudoeste: {
        endpoint: "/sudoeste",
        filename: "sudoeste_inicial_processado.xlsx",
        requiredCount: 3,
        fields: [
            {
                name: "base",
                formKey: "base",
                label: "Arquivo Base",
                hint: "Aceita CSV ou XLSX."
            },
            {
                name: "recebimento",
                formKey: "recebimento",
                label: "Arquivo de Recebimento",
                hint: "Aceita CSV ou XLSX."
            },
            {
                name: "denodo",
                formKey: "denodo",
                label: "Arquivo Denodo",
                hint: "Aceita CSV ou XLSX."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo os anexos obrigatorios." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 50, status: "Processando planilhas...", detail: "Lendo e preparando os dados para cruzamento." },
            { delayMs: 2600, progress: 65, status: "Cruzando recebimento com base...", detail: "Aplicando as regras de correspondencia." },
            { delayMs: 4200, progress: 80, status: "Verificando protocolos na denodo...", detail: "Consultando as correspondencias para protocolo." },
            { delayMs: 6200, progress: 92, status: "Gerando arquivo final...", detail: "Montando o arquivo final para download." }
        ]
    },
    sudoeste_direto: {
        endpoint: "/sudoeste-direto",
        filename: "sudoeste_direto_processado.xlsx",
        requiredCount: 2,
        fields: [
            {
                name: "processada",
                formKey: "processada",
                label: "Planilha Processada",
                hint: "Planilha gerada no fluxo Sudoeste - inicial."
            },
            {
                name: "direta",
                formKey: "direta",
                label: "Planilha Direta",
                hint: "Planilha direta do escritorio."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo as duas planilhas obrigatorias." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 55, status: "Processando planilhas...", detail: "Preparando dados da planilha processada e direta." },
            { delayMs: 2600, progress: 78, status: "Consolidando por CPF/CNPJ...", detail: "Aplicando match e consolidacao do fluxo direto." },
            { delayMs: 4200, progress: 92, status: "Gerando arquivo final...", detail: "Montando o relatorio sudoeste direto." }
        ]
    },
    sudoeste_indireto: {
        endpoint: "/sudoeste-indireto",
        filename: "sudoeste_indireto_processado.xlsx",
        requiredCount: 2,
        fields: [
            {
                name: "processada",
                formKey: "processada",
                label: "Planilha Processada",
                hint: "Planilha gerada no fluxo Sudoeste - inicial."
            },
            {
                name: "indireto",
                formKey: "indireto",
                label: "Planilha Indireto",
                hint: "Planilha de acionamento indireto."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo as duas planilhas obrigatorias." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 55, status: "Processando planilhas...", detail: "Preparando dados da planilha processada e indireto." },
            { delayMs: 2600, progress: 78, status: "Consolidando por CPF/CNPJ...", detail: "Aplicando match e consolidacao do fluxo indireto." },
            { delayMs: 4200, progress: 92, status: "Gerando arquivo final...", detail: "Montando o relatorio sudoeste indireto." }
        ]
    },
    sudoeste_consolidado: {
        endpoint: "/sudoeste-consolidado",
        filename: "sudoeste_consolidado_processado.xlsx",
        requiredCount: 3,
        fields: [
            {
                name: "processada",
                formKey: "processada",
                label: "Planilha Processada",
                hint: "Planilha gerada no fluxo Sudoeste - inicial."
            },
            {
                name: "direta",
                formKey: "direta",
                label: "Planilha Direta",
                hint: "Planilha usada no fluxo Sudoeste - direto."
            },
            {
                name: "indireto",
                formKey: "indireto",
                label: "Planilha Indireto",
                hint: "Planilha usada no fluxo Sudoeste - indireto."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo as tres planilhas obrigatorias." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 55, status: "Processando direto e indireto...", detail: "Executando os fluxos existentes sem alterar regras." },
            { delayMs: 2600, progress: 80, status: "Montando arquivo consolidado...", detail: "Criando as abas Direto e Indireto no mesmo Excel." },
            { delayMs: 4200, progress: 92, status: "Gerando arquivo final...", detail: "Preparando o relatorio consolidado para download." }
        ]
    },
    sudoeste_processadorv2: {
        endpoint: "/sudoeste-processadorv2",
        filename: "sudoeste_processadorv2_resultado.xlsx",
        requiredCount: 3,
        fields: [
            {
                name: "consolidada",
                formKey: "consolidada",
                label: "Planilha Consolidada",
                hint: "Planilha com clientes que ja pagaram (consolidados)."
            },
            {
                name: "direta",
                formKey: "direta",
                label: "Planilha Direta",
                hint: "Planilha de solicitacoes diretas."
            },
            {
                name: "indireto",
                formKey: "indireto",
                label: "Planilha Indireto",
                hint: "Planilha de solicitacoes indiretas."
            }
        ],
        progressSteps: [
            { delayMs: 0, progress: 10, status: "Validando arquivos...", detail: "Conferindo as tres planilhas obrigatorias." },
            { delayMs: 350, progress: 25, status: "Enviando arquivos...", detail: "Transferindo os arquivos para o servidor." },
            { delayMs: 1200, progress: 50, status: "Lendo consolidado e solicitacoes...", detail: "Preparando dados para busca cruzada." },
            { delayMs: 2200, progress: 70, status: "Filtrando consolidado...", detail: "Mantendo clientes em direto ou indireto." },
            { delayMs: 3200, progress: 85, status: "Separando por tipo...", detail: "Criando abas Direto e Indireto com dados individualizados." },
            { delayMs: 4200, progress: 92, status: "Gerando arquivo final...", detail: "Preparando relatorio do processadorv2 para download." }
        ]
    }
};

const form = document.getElementById("upload-form");
const tipoSelect = document.getElementById("tipo");
const inputsContainer = document.getElementById("inputs-container");
const requirementsText = document.getElementById("requirements-text");
const submitButton = document.getElementById("submit-button");
const messageBox = document.getElementById("message");
const progressBar = document.getElementById("progress-bar");
const statusChip = document.getElementById("status-chip");
const statusText = document.getElementById("status-text");
const statusDetail = document.getElementById("status-detail");
const statusFile = document.getElementById("status-file");

let currentProgress = 0;
let progressRunId = 0;
let progressTimers = [];
const debugParams = new URLSearchParams(window.location.search);
const DEBUG_UPLOAD = window.localStorage.getItem("uploadDebug") === "1" || debugParams.get("debugUpload") === "1";

function debugLog(event, payload = {}) {
    if (!DEBUG_UPLOAD) {
        return;
    }

    console.info(`[upload-debug] ${event}`, payload);
}

function renderFields() {
    const tipo = tipoSelect.value;
    const config = FORM_CONFIG[tipo];

    requirementsText.textContent = `${config.requiredCount} arquivo(s): ${config.fields
        .map((field) => field.label)
        .join(", ")}`;

    inputsContainer.innerHTML = config.fields
        .map(
            (field) => `
                <div class="file-field">
                    <label for="${field.name}">
                        ${field.label}
                        <span class="required-badge">Obrigatorio</span>
                    </label>
                    <input
                        id="${field.name}"
                        type="file"
                        name="${field.name}"
                        data-field-name="${field.name}"
                        data-form-key="${field.formKey || field.name}"
                        data-flow="${tipo}"
                        required
                    >
                    <span class="hint">${field.hint}</span>
                </div>
            `
        )
        .join("");

    debugLog("campos renderizados", {
        tipo,
        endpoint: config.endpoint,
        campos_esperados: config.fields.map((field) => ({
            name: field.name,
            formKey: field.formKey || field.name
        }))
    });

    clearFeedback();
}

function clearProgressTimers() {
    for (const timerId of progressTimers) {
        clearTimeout(timerId);
    }
    progressTimers = [];
}

function getChipLabel(state) {
    if (state === "is-success") {
        return "Concluido";
    }
    if (state === "is-error") {
        return "Erro";
    }
    return "Em andamento";
}

function setFeedbackState(state, text, progress, detail = "", fileName = "") {
    const clampedProgress = Math.max(0, Math.min(100, progress));
    currentProgress = clampedProgress;
    progressBar.style.width = `${clampedProgress}%`;
    progressBar.setAttribute("aria-valuenow", `${clampedProgress}`);
    statusChip.textContent = getChipLabel(state);
    statusText.textContent = text;
    statusDetail.textContent = detail;
    statusFile.textContent = fileName ? `Arquivo: ${fileName}` : "";
    messageBox.className = `message is-visible ${state}`;
}

function clearFeedback() {
    progressRunId += 1;
    clearProgressTimers();
    currentProgress = 0;
    progressBar.style.width = "0%";
    progressBar.setAttribute("aria-valuenow", "0");
    statusChip.textContent = "";
    statusText.textContent = "";
    statusDetail.textContent = "";
    statusFile.textContent = "";
    messageBox.className = "message";
}

function updateProgress(progress, status, detail = "") {
    const nextProgress = Math.max(currentProgress, progress);
    setFeedbackState("is-progress", status, nextProgress, detail);
}

function scheduleProgress(runId, delayMs, progress, status, detail = "") {
    const timerId = setTimeout(() => {
        if (runId !== progressRunId) {
            return;
        }
        updateProgress(progress, status, detail);
    }, delayMs);
    progressTimers.push(timerId);
}

function startProgress(config) {
    progressRunId += 1;
    const runId = progressRunId;
    clearProgressTimers();
    const steps = config.progressSteps || [];

    if (steps.length === 0) {
        setFeedbackState("is-progress", "Processando...", 15, "Preparando dados.");
        return;
    }

    const [firstStep, ...otherSteps] = steps;
    setFeedbackState(
        "is-progress",
        firstStep.status,
        firstStep.progress,
        firstStep.detail || ""
    );

    for (const step of otherSteps) {
        scheduleProgress(
            runId,
            step.delayMs,
            step.progress,
            step.status,
            step.detail || ""
        );
    }
}

function completeProgress(fileName) {
    clearProgressTimers();
    setFeedbackState(
        "is-success",
        "Processamento concluido com sucesso.",
        100,
        "Download iniciado.",
        fileName
    );
}

function failProgress(status, detail = "") {
    clearProgressTimers();
    const frozenProgress = currentProgress > 0 ? currentProgress : 15;
    setFeedbackState("is-error", status, frozenProgress, detail);
}

function setLoading(isLoading, text) {
    submitButton.disabled = isLoading;
    submitButton.textContent = isLoading ? text : "Enviar arquivos";
}

function buildFormData(tipo, config) {
    const formData = new FormData();
    const missing = [];
    const appended = [];

    debugLog("iniciando montagem do formData", {
        tipo,
        endpoint: config.endpoint,
        campos_esperados: config.fields.map((field) => field.formKey || field.name)
    });

    for (const field of config.fields) {
        const input = inputsContainer.querySelector(
            `input[type="file"][data-field-name="${field.name}"]`
        ) || document.getElementById(field.name);
        const file = input?.files?.[0];
        const formKey = field.formKey || input?.dataset?.formKey || field.name;

        debugLog("campo avaliado", {
            tipo,
            campo_config: field.name,
            chave_multipart: formKey,
            input_id: input?.id || null,
            input_name: input?.name || null,
            dataset_field_name: input?.dataset?.fieldName || null,
            dataset_form_key: input?.dataset?.formKey || null,
            arquivo: file?.name || null
        });

        if (!file) {
            missing.push(field.label);
            continue;
        }

        formData.append(formKey, file, file.name);
        appended.push({
            key: formKey,
            file: file.name,
            size: file.size,
            type: file.type
        });

        debugLog("arquivo adicionado ao formData", {
            tipo,
            chave_multipart: formKey,
            arquivo: file.name,
            size: file.size,
            type: file.type
        });
    }

    if (missing.length > 0) {
        debugLog("montagem do formData com campos ausentes", {
            tipo,
            campos_ausentes: missing
        });
        throw new Error(`Envie todos os arquivos obrigatorios: ${missing.join(", ")}.`);
    }

    debugLog("montagem do formData concluida", {
        tipo,
        anexos: appended
    });

    return formData;
}

function getFilenameFromDisposition(contentDisposition, fallbackName) {
    if (!contentDisposition) {
        return fallbackName;
    }

    const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match?.[1]) {
        return decodeURIComponent(utf8Match[1]);
    }

    const simpleMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
    if (simpleMatch?.[1]) {
        return simpleMatch[1];
    }

    return fallbackName;
}

function formatValidationDetail(detail) {
    if (!detail || typeof detail !== "object") {
        return "";
    }

    const location = Array.isArray(detail.loc)
        ? detail.loc.filter((part) => part !== "body").join(".")
        : "";
    const rawMessage = typeof detail.msg === "string" ? detail.msg.trim() : "";
    const message = rawMessage === "Field required" ? "campo obrigatorio" : rawMessage;

    if (!message) {
        return "";
    }

    return location ? `${location}: ${message}` : message;
}

async function extractErrorMessage(response) {
    try {
        const data = await response.json();

        if (Array.isArray(data?.detail) && data.detail.length > 0) {
            const details = data.detail
                .map((detail) => formatValidationDetail(detail))
                .filter(Boolean);

            if (details.length > 0) {
                return details.join(" | ");
            }
        }

        if (typeof data?.detail === "string" && data.detail.trim()) {
            return data.detail;
        }
    } catch (error) {
        try {
            const text = await response.text();
            if (text?.trim()) {
                return text.trim();
            }
        } catch (readError) {
            return `Falha no envio: ${response.status} ${response.statusText}`.trim();
        }
    }

    return `Falha no envio: ${response.status} ${response.statusText}`.trim();
}

async function handleSubmit(event) {
    event.preventDefault();

    const tipo = tipoSelect.value;
    const config = FORM_CONFIG[tipo];

    try {
        setLoading(true, "Enviando...");
        startProgress(config);

        debugLog("submissao iniciada", {
            tipo,
            endpoint: config.endpoint
        });

        const formData = buildFormData(tipo, config);
        updateProgress(30, "Enviando arquivos...", "Transferindo os arquivos para o servidor.");

        const response = await fetch(config.endpoint, {
            method: "POST",
            body: formData
        });
        debugLog("resposta recebida", {
            tipo,
            endpoint: config.endpoint,
            status: response.status,
            statusText: response.statusText,
            requestId: response.headers.get("X-Request-ID")
        });

        if (!response.ok) {
            throw new Error(await extractErrorMessage(response));
        }

        updateProgress(95, "Gerando arquivo final...", "Finalizando o relatorio para download.");
        const blob = await response.blob();
        const filename = getFilenameFromDisposition(
            response.headers.get("Content-Disposition"),
            config.filename
        );

        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(url);

        completeProgress(filename);
    } catch (error) {
        const detail = error.message || "Nao foi possivel concluir o processamento.";
        debugLog("erro na submissao", {
            tipo,
            endpoint: config.endpoint,
            erro: detail
        });
        failProgress("Erro ao processar relatorio.", detail);
    } finally {
        setLoading(false);
    }
}

tipoSelect.addEventListener("change", renderFields);
form.addEventListener("submit", handleSubmit);

renderFields();

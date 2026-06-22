const source = document.querySelector("#source");
const runButton = document.querySelector("#runButton");
const resetButton = document.querySelector("#resetButton");
const uploadButton = document.querySelector("#uploadButton");
const rulesFile = document.querySelector("#rulesFile");
const rulesPanel = document.querySelector("#rulesPanel");
const rulesMeta = document.querySelector("#rulesMeta");
const rulesText = document.querySelector("#rulesText");
const useRulesButton = document.querySelector("#useRulesButton");
const statusBadge = document.querySelector("#status");
const client = document.querySelector("#client");
const total = document.querySelector("#total");
const state = document.querySelector("#state");
const logs = document.querySelector("#logs");
const errors = document.querySelector("#errors");
const tokens = document.querySelector("#tokens");
const lexemeGroups = document.querySelector("#lexemeGroups");
const tokenDefinitions = document.querySelector("#tokenDefinitions");
const regexDefinitions = document.querySelector("#regexDefinitions");
const nfaDefinitions = document.querySelector("#nfaDefinitions");
const dfaDefinitions = document.querySelector("#dfaDefinitions");
const transitionTables = document.querySelector("#transitionTables");
let uploadedDslDraft = "";

const TOKEN_DEFINITIONS = [
    {type: "RESERVED", description: "Palabra reservada del DSL que activa una instruccion del workflow.", example: "PEDIDO, VALIDAR, SI"},
    {type: "IDENTIFIER", description: "Nombre de campo, variable, recurso o estado del proceso logistico.", example: "cliente, stock, repartidor"},
    {type: "NUMBER", description: "Valor numerico entero o decimal usado en datos y condiciones.", example: "80, 4, 50"},
    {type: "STRING", description: "Cadena literal encerrada entre comillas dobles.", example: "\"Carlos\""},
    {type: "LBRACE", description: "Llave de apertura de bloque.", example: "{"},
    {type: "RBRACE", description: "Llave de cierre de bloque.", example: "}"},
    {type: "COLON", description: "Separador entre propiedad y valor.", example: ":"},
    {type: "OPERATOR", description: "Operador relacional para condiciones.", example: ">, <, >=, <="},
];

const REGEX_DEFINITIONS = [
    {type: "RESERVED", regex: "(PEDIDO|VALIDAR|SI|ASIGNAR|INICIAR|FINALIZAR)", explanation: "Reconoce las palabras con significado fijo dentro del DSL."},
    {type: "IDENTIFIER", regex: "[A-Za-z_][A-Za-z0-9_]*", explanation: "Reconoce nombres que empiezan con letra o guion bajo y continuan con letras, digitos o guion bajo."},
    {type: "NUMBER", regex: "[0-9]+(\\.[0-9]+)?", explanation: "Reconoce numeros enteros y decimales positivos."},
    {type: "STRING", regex: "\"([^\"\\n])*\"", explanation: "Reconoce texto entre comillas dobles sin salto de linea interno."},
    {type: "LBRACE", regex: "\\{", explanation: "Reconoce apertura de bloque."},
    {type: "RBRACE", regex: "\\}", explanation: "Reconoce cierre de bloque."},
    {type: "COLON", regex: ":", explanation: "Reconoce asignacion propiedad-valor."},
    {type: "OPERATOR", regex: "(>|<|>=|<=|==|!=)", explanation: "Reconoce comparadores logicos."},
];

const AUTOMATA = [
    {
        type: "IDENTIFIER",
        nfa: "q0 --letra/_--> q1; q1 --letra/digito/_--> q1; q1 es final.",
        dfa: "D0 espera letra o _; D1 consume letras, digitos o _ hasta encontrar separador.",
        headers: ["Estado", "letra/_", "digito", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D1", "D1", "Finalizar token"]],
    },
    {
        type: "NUMBER",
        nfa: "q0 --digito--> q1; q1 --digito--> q1; q1 --'.'--> q2; q2 --digito--> q3; q3 --digito--> q3.",
        dfa: "D0 inicia numero; D1 acepta entero; D2 espera decimal; D3 acepta decimal.",
        headers: ["Estado", "digito", ".", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D1", "D2", "Finalizar token"], ["D2", "D3", "-", "Error"], ["D3", "D3", "-", "Finalizar token"]],
    },
    {
        type: "STRING",
        nfa: "q0 --comilla--> q1; q1 --caracter distinto de comilla--> q1; q1 --comilla--> q2.",
        dfa: "D0 espera apertura; D1 acumula contenido; D2 acepta cadena.",
        headers: ["Estado", "comilla", "caracter", "fin"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D2", "D1", "Error"], ["D2", "Final", "-", "-"]],
    },
    {
        type: "OPERATOR",
        nfa: "q0 -->,<,=,!--> q1; q1 --=--> q2 opcional.",
        dfa: "D0 espera operador inicial; D1 acepta operador simple; D2 acepta operador compuesto.",
        headers: ["Estado", ">/< / = / !", "=", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "-", "D2", "Finalizar token"], ["D2", "-", "-", "Finalizar token"]],
    },
];

function setStatus(success) {
    statusBadge.className = `status ${success ? "ok" : "bad"}`;
    statusBadge.textContent = success ? "Valido" : "Con errores";
    state.textContent = success ? "Workflow aprobado" : "Revisar errores";
}

function renderList(element, items, emptyText) {
    element.innerHTML = "";
    const values = items && items.length ? items : [emptyText];
    values.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        element.appendChild(li);
    });
}

function renderTokens(items) {
    tokens.innerHTML = "";
    if (!items || !items.length) {
        const row = document.createElement("tr");
        row.innerHTML = `<td colspan="4">Sin tokens para mostrar</td>`;
        tokens.appendChild(row);
        return;
    }

    const grouped = items.reduce((acc, token) => {
        if (!acc[token.type]) {
            acc[token.type] = {
                type: token.type,
                lexemes: new Set(),
                positions: [],
                count: 0,
            };
        }
        acc[token.type].lexemes.add(token.lexeme);
        acc[token.type].positions.push(`${token.line}:${token.column}`);
        acc[token.type].count += 1;
        return acc;
    }, {});

    Object.values(grouped).forEach((group) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${group.type}</td>
            <td>${[...group.lexemes].join(", ")}</td>
            <td>${group.count}</td>
            <td>${group.positions.join(", ")}</td>
        `;
        tokens.appendChild(row);
    });
}

function uniqueLexemes(items, type) {
    return [...new Set((items || []).filter((token) => token.type === type).map((token) => token.lexeme))];
}

function renderAnalysis(items) {
    const tokensByType = TOKEN_DEFINITIONS.map((definition) => ({
        ...definition,
        lexemes: uniqueLexemes(items, definition.type),
    }));

    lexemeGroups.innerHTML = tokensByType.map((group) => `
        <div class="mini-block">
            <strong>${group.type}</strong>
            <p>${group.lexemes.length ? group.lexemes.join(", ") : "Sin lexemas detectados aun."}</p>
        </div>
    `).join("");

    tokenDefinitions.innerHTML = TOKEN_DEFINITIONS.map((definition) => `
        <tr>
            <td>${definition.type}</td>
            <td>${definition.description}</td>
            <td>${definition.example}</td>
        </tr>
    `).join("");

    regexDefinitions.innerHTML = REGEX_DEFINITIONS.map((definition) => `
        <div class="mini-block">
            <strong>${definition.type}</strong>
            <code>${definition.regex}</code>
            <p>${definition.explanation}</p>
        </div>
    `).join("");

    nfaDefinitions.innerHTML = AUTOMATA.map((item) => `
        <div class="mini-block">
            <strong>AFND ${item.type}</strong>
            <p>${item.nfa}</p>
        </div>
    `).join("");

    dfaDefinitions.innerHTML = AUTOMATA.map((item) => `
        <div class="mini-block">
            <strong>AFD ${item.type}</strong>
            <p>${item.dfa}</p>
        </div>
    `).join("");

    transitionTables.innerHTML = AUTOMATA.map((item) => `
        <div class="transition-block">
            <strong>${item.type}</strong>
            <div class="table-wrap compact-table">
                <table>
                    <thead>
                        <tr>${item.headers.map((header) => `<th>${header}</th>`).join("")}</tr>
                    </thead>
                    <tbody>
                        ${item.rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}
                    </tbody>
                </table>
            </div>
        </div>
    `).join("");
}

async function compile() {
    runButton.disabled = true;
    runButton.textContent = "Ejecutando...";

    try {
        const response = await fetch("/compile", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({source: source.value}),
        });
        const result = await response.json();
        setStatus(result.success);
        client.textContent = result.order?.cliente ?? "-";
        total.textContent = result.order?.total ?? "-";
        renderList(logs, result.logs, "Aun no hay logs.");
        renderList(errors, result.errors, "Sin errores.");
        renderTokens(result.tokens);
        renderAnalysis(result.tokens);
    } catch (error) {
        setStatus(false);
        renderList(errors, [error.message], "Error inesperado.");
    } finally {
        runButton.disabled = false;
        runButton.textContent = "Ejecutar workflow";
    }
}

async function uploadRules() {
    const file = rulesFile.files[0];
    if (!file) return;

    uploadButton.disabled = true;
    uploadButton.textContent = "Procesando...";

    const form = new FormData();
    form.append("rules", file);

    try {
        const response = await fetch("/upload-rules", {
            method: "POST",
            body: form,
        });
        const result = await response.json();
        if (!result.success) {
            throw new Error((result.errors || ["No se pudo procesar el archivo."]).join(" "));
        }
        rulesPanel.classList.remove("is-hidden");
        rulesMeta.textContent = `${result.filename} - ${result.message}`;
        rulesText.textContent = result.text;
        uploadedDslDraft = result.dsl_draft || "";
        if (uploadedDslDraft.trim()) {
            source.value = uploadedDslDraft.trim();
            await compile();
        }
    } catch (error) {
        rulesPanel.classList.remove("is-hidden");
        rulesMeta.textContent = "Error al procesar archivo";
        rulesText.textContent = error.message;
        uploadedDslDraft = "";
    } finally {
        uploadButton.disabled = false;
        uploadButton.textContent = "Subir reglas";
        rulesFile.value = "";
    }
}

runButton.addEventListener("click", compile);
resetButton.addEventListener("click", () => {
    source.value = window.DEFAULT_EXAMPLE;
});
uploadButton.addEventListener("click", () => rulesFile.click());
rulesFile.addEventListener("change", uploadRules);
useRulesButton.addEventListener("click", () => {
    if (uploadedDslDraft.trim()) {
        source.value = uploadedDslDraft.trim();
        compile();
    } else if (rulesText.textContent.trim()) {
        source.value = rulesText.textContent.trim();
        compile();
    }
});

renderTokens([]);
renderAnalysis([]);

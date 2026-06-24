const source = document.querySelector("#source");
const runButton = document.querySelector("#runButton");
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
const lexemeGroups = document.querySelector("#lexemeGroups");
const tokenDefinitions = document.querySelector("#tokenDefinitions");
const regexDefinitions = document.querySelector("#regexDefinitions");
const nfaDefinitions = document.querySelector("#nfaDefinitions");
const dfaDefinitions = document.querySelector("#dfaDefinitions");
const transitionTables = document.querySelector("#transitionTables");
const parserType = document.querySelector("#parserType");
const grammarRules = document.querySelector("#grammarRules");
const syntaxTree = document.querySelector("#syntaxTree");
const treeLegend = document.querySelector("#treeLegend");
const symbolTable = document.querySelector("#symbolTable");
const semanticChecks = document.querySelector("#semanticChecks");
const semanticAttributes = document.querySelector("#semanticAttributes");
let uploadedDslDraft = "";

const GRAMMAR = [
    ["programa", "sentencia*"],
    ["sentencia", "pedido | validación | condicional | acción"],
    ["pedido", "PEDIDO { propiedad* }"],
    ["propiedad", "IDENTIFIER : valor"],
    ["valor", "STRING | NUMBER | IDENTIFIER"],
    ["validación", "VALIDAR IDENTIFIER"],
    ["condicional", "SI condición { sentencia* }"],
    ["condición", "IDENTIFIER OPERATOR valor"],
    ["acción", "(ASIGNAR | INICIAR | FINALIZAR) IDENTIFIER"],
];

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
        headers: ["Estado", "letra/_", "digito", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D1", "D1", "Finalizar token"]],
    },
    {
        type: "NUMBER",
        headers: ["Estado", "digito", ".", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D1", "D2", "Finalizar token"], ["D2", "D3", "-", "Error"], ["D3", "D3", "-", "Finalizar token"]],
    },
    {
        type: "STRING",
        headers: ["Estado", "comilla", "caracter", "fin"],
        rows: [["D0", "D1", "-", "-"], ["D1", "D2", "D1", "Error"], ["D2", "Final", "-", "-"]],
    },
    {
        type: "OPERATOR",
        headers: ["Estado", ">/< / = / !", "=", "otro"],
        rows: [["D0", "D1", "-", "-"], ["D1", "-", "D2", "Finalizar token"], ["D2", "-", "-", "Finalizar token"]],
    },
];

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
    })[character]);
}

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

function uniqueLexemes(items, type) {
    return [...new Set((items || []).filter((token) => token.type === type).map((token) => token.lexeme))];
}

function automatonGraph(type, mode) {
    const prefix = mode === "nfa" ? "q" : "D";
    const state = (id, x, final = false) => ({id, label: `${prefix}${id}`, x, y: 92, final});
    const graphs = {
        IDENTIFIER: {
            width: 430,
            states: [state(0, 90), state(1, 320, true)],
            edges: [
                {from: 0, to: 1, label: "letra / _"},
                {from: 1, to: 1, label: "letra / dígito / _", loop: true},
            ],
        },
        NUMBER: {
            width: 590,
            states: [state(0, 65), state(1, 210, true), state(2, 355), state(3, 520, true)],
            edges: [
                {from: 0, to: 1, label: "dígito"},
                {from: 1, to: 1, label: "dígito", loop: true},
                {from: 1, to: 2, label: "."},
                {from: 2, to: 3, label: "dígito"},
                {from: 3, to: 3, label: "dígito", loop: true},
            ],
        },
        STRING: {
            width: 520,
            states: [state(0, 70), state(1, 260), state(2, 450, true)],
            edges: [
                {from: 0, to: 1, label: "comilla"},
                {from: 1, to: 1, label: "otro carácter", loop: true},
                {from: 1, to: 2, label: "comilla"},
            ],
        },
        OPERATOR: {
            width: 520,
            states: [state(0, 70), state(1, 260, true), state(2, 450, true)],
            edges: [
                {from: 0, to: 1, label: ">, <, =, !"},
                {from: 1, to: 2, label: "="},
            ],
        },
    };
    return graphs[type];
}

function createAutomatonSvg(type, mode, index) {
    const graph = automatonGraph(type, mode);
    const markerId = `automaton-arrow-${mode}-${index}`;
    const svg = svgElement("svg", {
        class: "automaton-svg",
        viewBox: `0 0 ${graph.width} 190`,
        role: "img",
        "aria-label": `${mode === "nfa" ? "AFND" : "AFD"} para ${type}`,
    });
    const defs = svgElement("defs");
    const marker = svgElement("marker", {
        id: markerId,
        markerWidth: 8,
        markerHeight: 8,
        refX: 7,
        refY: 4,
        orient: "auto",
    });
    marker.appendChild(svgElement("path", {d: "M0,0 L8,4 L0,8 Z", class: "automaton-arrowhead"}));
    defs.appendChild(marker);
    svg.appendChild(defs);

    const states = new Map(graph.states.map((item) => [item.id, item]));
    const radius = 29;
    const initial = graph.states[0];
    svg.appendChild(svgElement("line", {
        x1: initial.x - 72,
        y1: initial.y,
        x2: initial.x - radius - 3,
        y2: initial.y,
        class: "automaton-edge",
        "marker-end": `url(#${markerId})`,
    }));

    graph.edges.forEach((edge) => {
        const from = states.get(edge.from);
        const to = states.get(edge.to);
        if (edge.loop) {
            svg.appendChild(svgElement("path", {
                d: `M ${from.x - 13} ${from.y - 26} C ${from.x - 55} ${from.y - 82}, ${from.x + 55} ${from.y - 82}, ${from.x + 13} ${from.y - 26}`,
                class: "automaton-edge",
                fill: "none",
                "marker-end": `url(#${markerId})`,
            }));
            const label = svgElement("text", {x: from.x, y: from.y - 70, class: "automaton-label"});
            label.textContent = edge.label;
            svg.appendChild(label);
            return;
        }

        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const distance = Math.hypot(dx, dy);
        const ux = dx / distance;
        const uy = dy / distance;
        svg.appendChild(svgElement("line", {
            x1: from.x + ux * radius,
            y1: from.y + uy * radius,
            x2: to.x - ux * (radius + 4),
            y2: to.y - uy * (radius + 4),
            class: "automaton-edge",
            "marker-end": `url(#${markerId})`,
        }));
        const label = svgElement("text", {
            x: (from.x + to.x) / 2,
            y: (from.y + to.y) / 2 - 10,
            class: "automaton-label",
        });
        label.textContent = edge.label;
        svg.appendChild(label);
    });

    graph.states.forEach((item) => {
        const group = svgElement("g", {class: "automaton-state"});
        group.appendChild(svgElement("circle", {cx: item.x, cy: item.y, r: radius}));
        if (item.final) group.appendChild(svgElement("circle", {cx: item.x, cy: item.y, r: radius - 5}));
        const label = svgElement("text", {x: item.x, y: item.y + 1});
        label.textContent = item.label;
        group.appendChild(label);
        svg.appendChild(group);
    });
    return svg;
}

function renderAutomata(container, mode) {
    container.innerHTML = "";
    AUTOMATA.forEach((item, index) => {
        const block = document.createElement("div");
        block.className = "automaton-block";
        const title = document.createElement("strong");
        title.textContent = `${mode === "nfa" ? "AFND" : "AFD"} ${item.type}`;
        block.appendChild(title);
        block.appendChild(createAutomatonSvg(item.type, mode, index));
        container.appendChild(block);
    });
}

function renderAnalysis(items) {
    const tokensByType = TOKEN_DEFINITIONS.map((definition) => ({
        ...definition,
        lexemes: uniqueLexemes(items, definition.type),
    }));

    lexemeGroups.innerHTML = tokensByType.map((group) => `
        <div class="mini-block">
            <strong>${group.type}</strong>
            <p>${group.lexemes.length ? group.lexemes.map(escapeHtml).join(", ") : "Sin lexemas detectados aún."}</p>
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

    renderAutomata(nfaDefinitions, "nfa");
    renderAutomata(dfaDefinitions, "dfa");

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

function renderGrammar(parserName = "descendente recursivo LL(1)") {
    parserType.textContent = parserName;
    grammarRules.innerHTML = GRAMMAR.map(([left, right]) => `
        <div class="grammar-rule">
            <code>&lt;${escapeHtml(left)}&gt;</code>
            <span>→</span>
            <code>${escapeHtml(right)}</code>
        </div>
    `).join("");
}

const NODE_DESCRIPTIONS = {
    Programa: "Nodo inicial que agrupa todo el workflow.",
    Pedido: "Declaración de los datos del pedido.",
    Propiedad: "Campo declarado dentro de PEDIDO.",
    Texto: "Valor textual o identificador literal.",
    Numero: "Valor numérico entero o decimal.",
    Validacion: "Comprobación de un campo del pedido.",
    Identificador: "Referencia a un símbolo declarado.",
    Condicional: "Decisión introducida por SI.",
    Condicion: "Comparación que produce un booleano.",
    Operador: "Operador relacional de la comparación.",
    Bloque: "Secuencia de sentencias condicionadas.",
    Accion: "Operación ASIGNAR, INICIAR o FINALIZAR.",
    Objetivo: "Recurso o proceso afectado por una acción.",
    ErrorSintactico: "Fragmento que no cumple la gramática.",
};

function layoutSyntaxTree(root) {
    const nodes = [];
    const links = [];
    const horizontalGap = 118;
    const verticalGap = 118;
    let leafIndex = 0;
    let maxDepth = 0;

    function visit(node, depth, parent = null) {
        maxDepth = Math.max(maxDepth, depth);
        const children = node.children || [];
        const placedChildren = children.map((child) => visit(child, depth + 1, node));
        const x = placedChildren.length
            ? placedChildren.reduce((sum, child) => sum + child.x, 0) / placedChildren.length
            : 62 + leafIndex++ * horizontalGap;
        const placed = {node, x, y: 55 + depth * verticalGap, parent};
        nodes.push(placed);
        placedChildren.forEach((child) => links.push({from: placed, to: child}));
        return placed;
    }

    const rootPosition = visit(root, 0);
    return {
        nodes,
        links,
        rootX: rootPosition.x,
        width: Math.max(720, 124 + Math.max(leafIndex - 1, 0) * horizontalGap),
        height: 110 + maxDepth * verticalGap,
    };
}

function svgElement(name, attributes = {}) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
}

function renderGraphicalTree(root) {
    const layout = layoutSyntaxTree(root);
    const svg = svgElement("svg", {
        class: "syntax-tree-svg",
        viewBox: `0 0 ${layout.width} ${layout.height}`,
        width: layout.width,
        height: layout.height,
        role: "img",
        "aria-label": "Árbol sintáctico abstracto del workflow",
    });

    const linksGroup = svgElement("g", {class: "tree-links"});
    layout.links.forEach(({from, to}) => {
        linksGroup.appendChild(svgElement("line", {x1: from.x, y1: from.y + 38, x2: to.x, y2: to.y - 38}));
    });
    svg.appendChild(linksGroup);

    const nodesGroup = svgElement("g", {class: "tree-nodes"});
    layout.nodes.forEach(({node, x, y}) => {
        const group = svgElement("g", {
            class: `tree-node-group ${node.children?.length ? "non-terminal" : "terminal"}`,
            transform: `translate(${x} ${y})`,
            "data-node-id": node.id,
        });
        group.appendChild(svgElement("circle", {r: 38}));
        const title = svgElement("title");
        title.textContent = `${node.symbol}${node.lexeme ? `: ${node.lexeme}` : ""}${node.line ? ` · línea ${node.line}` : ""}`;
        group.appendChild(title);

        const symbol = svgElement("text", {class: "node-symbol", y: node.lexeme ? -4 : 4});
        symbol.textContent = node.symbol.length > 14 ? `${node.symbol.slice(0, 12)}…` : node.symbol;
        group.appendChild(symbol);
        if (node.lexeme) {
            const lexeme = svgElement("text", {class: "node-lexeme", y: 13});
            lexeme.textContent = node.lexeme.length > 12 ? `${node.lexeme.slice(0, 10)}…` : node.lexeme;
            group.appendChild(lexeme);
        }
        nodesGroup.appendChild(group);
    });
    svg.appendChild(nodesGroup);
    syntaxTree.appendChild(svg);
    syntaxTree.scrollLeft = Math.max(0, layout.rootX - syntaxTree.clientWidth / 2);
    syntaxTree.scrollTop = 0;
}

function renderTreeLegend(root) {
    const symbols = [];
    function collect(node) {
        if (!symbols.includes(node.symbol)) symbols.push(node.symbol);
        (node.children || []).forEach(collect);
    }
    collect(root);
    treeLegend.innerHTML = `
        <h4>Descripción de nodos</h4>
        <dl>${symbols.map((symbol) => `
            <div><dt>${escapeHtml(symbol)}</dt><dd>${escapeHtml(NODE_DESCRIPTIONS[symbol] || "Nodo de la gramática del DSL.")}</dd></div>
        `).join("")}</dl>
    `;
}

function renderSyntax(syntax) {
    renderGrammar(syntax?.parser || "descendente recursivo LL(1)");
    syntaxTree.innerHTML = "";
    treeLegend.innerHTML = "";
    if (!syntax?.tree) {
        syntaxTree.innerHTML = '<p class="empty-state">Ejecuta el workflow para construir el árbol.</p>';
        treeLegend.innerHTML = '<p class="legend-empty">La descripción de nodos aparecerá después del análisis.</p>';
        return;
    }
    renderGraphicalTree(syntax.tree);
    renderTreeLegend(syntax.tree);
}

function renderSemantic(semantic) {
    const symbols = semantic?.symbols || [];
    symbolTable.innerHTML = symbols.length ? symbols.map((symbol) => `
        <tr>
            <td><code>${escapeHtml(symbol.name)}</code></td>
            <td><span class="type-pill">${escapeHtml(symbol.type)}</span></td>
            <td>${escapeHtml(symbol.value)}</td>
            <td>${symbol.line || "-"}</td>
        </tr>
    `).join("") : '<tr><td colspan="4">Sin símbolos declarados.</td></tr>';

    const checks = semantic?.checks || [];
    semanticChecks.innerHTML = checks.length ? checks.map((check) => {
        const failed = check.startsWith("Fallo:");
        return `<li class="${failed ? "failed" : "passed"}"><span>${failed ? "×" : "✓"}</span>${escapeHtml(check)}</li>`;
    }).join("") : '<li class="empty-check">Ejecuta el workflow para evaluar sus reglas.</li>';

    const attributes = semantic?.attributes || [];
    semanticAttributes.innerHTML = attributes.length ? attributes.map((attribute) => `
        <tr data-valid="${attribute.synthesized.valid}">
            <td><strong>${escapeHtml(attribute.node)}</strong>${attribute.lexeme ? `<small>${escapeHtml(attribute.lexeme)}</small>` : ""}</td>
            <td><span>ámbito: <b>${escapeHtml(attribute.inherited.scope)}</b></span><span>contexto: <b>${escapeHtml(attribute.inherited.context)}</b></span></td>
            <td><span>tipo: <b>${escapeHtml(attribute.synthesized.type)}</b></span><span>valor: <b>${escapeHtml(attribute.synthesized.value)}</b></span><span class="validity">${attribute.synthesized.valid ? "válido" : "inválido"}</span></td>
            <td>${escapeHtml(attribute.rule)}</td>
        </tr>
    `).join("") : '<tr><td colspan="4">Sin atributos evaluados.</td></tr>';
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
        renderAnalysis(result.tokens);
        renderSyntax(result.syntax);
        renderSemantic(result.semantic);
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
        uploadedDslDraft = result.dsl_draft || "";
        if (uploadedDslDraft.trim()) {
            source.value = uploadedDslDraft.trim();
            rulesText.textContent = result.text;
            await compile();
        } else {
            rulesText.textContent = result.text;
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

renderAnalysis([]);
renderSyntax(null);
renderSemantic(null);

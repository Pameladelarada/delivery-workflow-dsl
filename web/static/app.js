const source = document.querySelector("#source");
const runButton = document.querySelector("#runButton");
const resetButton = document.querySelector("#resetButton");
const statusBadge = document.querySelector("#status");
const client = document.querySelector("#client");
const total = document.querySelector("#total");
const state = document.querySelector("#state");
const logs = document.querySelector("#logs");
const errors = document.querySelector("#errors");
const tokens = document.querySelector("#tokens");

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

    const groupedByType = items.reduce((groups, token) => {
        if (!groups.has(token.type)) {
            groups.set(token.type, new Map());
        }
        const lexemes = groups.get(token.type);
        if (!lexemes.has(token.lexeme)) {
            lexemes.set(token.lexeme, []);
        }
        lexemes.get(token.lexeme).push(token);
        return groups;
    }, new Map());

    groupedByType.forEach((lexemes, type) => {
        let firstTypeRow = true;

        lexemes.forEach((group) => {
            group.forEach((token, index) => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td>${firstTypeRow ? type : ""}</td>
                    <td>${index === 0 ? token.lexeme : ""}</td>
                    <td>${token.line}</td>
                    <td>${token.column}</td>
                `;
                tokens.appendChild(row);
                firstTypeRow = false;
            });
        });
    });
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
    } catch (error) {
        setStatus(false);
        renderList(errors, [error.message], "Error inesperado.");
    } finally {
        runButton.disabled = false;
        runButton.textContent = "Ejecutar workflow";
    }
}

runButton.addEventListener("click", compile);
resetButton.addEventListener("click", () => {
    source.value = window.DEFAULT_EXAMPLE;
});

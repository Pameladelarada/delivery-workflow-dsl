#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

enum class TokenType {
    Reserved,
    Identifier,
    Number,
    String,
    LBrace,
    RBrace,
    Colon,
    Operator,
    End
};

struct Token {
    TokenType type;
    std::string lexeme;
    int line;
    int column;
};

struct OrderValue {
    std::string raw;
    bool isNumber = false;
    double number = 0.0;
};

struct Condition {
    std::string left;
    std::string op;
    OrderValue right;
    int line = 0;
};

struct Action {
    std::string kind;
    std::string target;
    bool conditional = false;
    bool executed = true;
};

struct SyntaxNode {
    int id = 0;
    std::string symbol;
    std::string lexeme;
    int line = 0;
    std::vector<SyntaxNode> children;
};

struct SemanticAttribute {
    int nodeId = 0;
    std::string node;
    std::string lexeme;
    std::string inheritedScope;
    std::string inheritedContext;
    std::string synthesizedType;
    std::string synthesizedValue;
    bool valid = true;
    std::string rule;
};

struct SymbolEntry {
    std::string name;
    std::string type;
    std::string value;
    int line = 0;
};

static std::string tokenTypeName(TokenType type) {
    switch (type) {
        case TokenType::Reserved: return "RESERVED";
        case TokenType::Identifier: return "IDENTIFIER";
        case TokenType::Number: return "NUMBER";
        case TokenType::String: return "STRING";
        case TokenType::LBrace: return "LBRACE";
        case TokenType::RBrace: return "RBRACE";
        case TokenType::Colon: return "COLON";
        case TokenType::Operator: return "OPERATOR";
        case TokenType::End: return "END";
    }
    return "UNKNOWN";
}

static std::string jsonEscape(const std::string& text) {
    std::ostringstream out;
    for (char c : text) {
        switch (c) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << c; break;
        }
    }
    return out.str();
}

class Lexer {
public:
    explicit Lexer(std::string source) : source_(std::move(source)) {}

    std::vector<Token> scan() {
        while (!isAtEnd()) {
            startColumn_ = column_;
            char c = advance();
            if (c == ' ' || c == '\r' || c == '\t') continue;
            if (c == '\n') {
                line_++;
                column_ = 1;
                continue;
            }
            if (std::isalpha(static_cast<unsigned char>(c)) || c == '_') {
                identifier(c);
            } else if (std::isdigit(static_cast<unsigned char>(c))) {
                number(c);
            } else if (c == '"') {
                stringLiteral();
            } else if (c == '{') {
                add(TokenType::LBrace, "{");
            } else if (c == '}') {
                add(TokenType::RBrace, "}");
            } else if (c == ':') {
                add(TokenType::Colon, ":");
            } else if (isOperatorStart(c)) {
                op(c);
            } else {
                throw std::runtime_error("Caracter no reconocido '" + std::string(1, c) +
                                         "' en linea " + std::to_string(line_));
            }
        }
        tokens_.push_back({TokenType::End, "", line_, column_});
        return tokens_;
    }

private:
    std::string source_;
    std::vector<Token> tokens_;
    size_t current_ = 0;
    int line_ = 1;
    int column_ = 1;
    int startColumn_ = 1;
    std::set<std::string> reserved_ = {"PEDIDO", "VALIDAR", "SI", "ASIGNAR", "INICIAR", "FINALIZAR"};

    bool isAtEnd() const { return current_ >= source_.size(); }

    char advance() {
        column_++;
        return source_[current_++];
    }

    char peek() const {
        if (isAtEnd()) return '\0';
        return source_[current_];
    }

    void add(TokenType type, const std::string& lexeme) {
        tokens_.push_back({type, lexeme, line_, startColumn_});
    }

    bool isOperatorStart(char c) const {
        return c == '>' || c == '<' || c == '=' || c == '!';
    }

    void identifier(char first) {
        std::string value(1, first);
        while (std::isalnum(static_cast<unsigned char>(peek())) || peek() == '_') {
            value.push_back(advance());
        }
        if (reserved_.count(value)) add(TokenType::Reserved, value);
        else add(TokenType::Identifier, value);
    }

    void number(char first) {
        std::string value(1, first);
        while (std::isdigit(static_cast<unsigned char>(peek()))) value.push_back(advance());
        if (peek() == '.') {
            value.push_back(advance());
            while (std::isdigit(static_cast<unsigned char>(peek()))) value.push_back(advance());
        }
        add(TokenType::Number, value);
    }

    void stringLiteral() {
        std::string value;
        while (!isAtEnd() && peek() != '"') {
            char c = advance();
            if (c == '\n') {
                line_++;
                column_ = 1;
            }
            value.push_back(c);
        }
        if (isAtEnd()) throw std::runtime_error("Cadena sin cerrar en linea " + std::to_string(line_));
        advance();
        add(TokenType::String, value);
    }

    void op(char first) {
        std::string value(1, first);
        if ((first == '>' || first == '<' || first == '=' || first == '!') && peek() == '=') {
            value.push_back(advance());
        }
        add(TokenType::Operator, value);
    }
};

class Parser {
public:
    explicit Parser(std::vector<Token> tokens) : tokens_(std::move(tokens)) {
        tree_ = makeNode("Programa", "", 1);
    }

    void parse() {
        while (!check(TokenType::End)) {
            if (check(TokenType::RBrace)) {
                errors_.push_back("Error sintactico: '}' sin bloque de apertura en linea " +
                                  std::to_string(tokens_[current_].line));
                advance();
                continue;
            }
            tree_.children.push_back(statement(false, true));
        }
    }

    const std::map<std::string, OrderValue>& order() const { return order_; }
    const std::vector<Action>& actions() const { return actions_; }
    const std::vector<std::string>& validations() const { return validations_; }
    const std::vector<std::string>& errors() const { return errors_; }
    const std::vector<std::string>& logs() const { return logs_; }
    const SyntaxNode& tree() const { return tree_; }
    const std::vector<SemanticAttribute>& attributes() const { return attributes_; }
    const std::vector<SymbolEntry>& symbols() const { return symbols_; }
    const std::vector<std::string>& semanticChecks() const { return semanticChecks_; }

    void semanticAnalysis() {
        std::set<std::string> allowedValidations = {"stock", "direccion", "pago", "cliente", "producto", "total"};

        symbols_.clear();
        attributes_.clear();
        semanticChecks_.clear();
        for (const auto& item : order_) {
            symbols_.push_back({item.first, item.second.isNumber ? "numero" : "texto", item.second.raw,
                                orderLines_.count(item.first) ? orderLines_[item.first] : 0});
        }

        if (order_.empty()) {
            errors_.push_back("Error semantico: el programa debe definir un bloque PEDIDO.");
            semanticChecks_.push_back("Fallo: no existe un bloque PEDIDO que defina el ambito global.");
        } else {
            semanticChecks_.push_back("Correcto: PEDIDO define " + std::to_string(order_.size()) +
                                      " simbolos en el ambito global.");
        }

        for (const std::string& field : validations_) {
            if (!allowedValidations.count(field)) {
                errors_.push_back("Error semantico: VALIDAR " + field + " no pertenece al dominio permitido.");
                semanticChecks_.push_back("Fallo: '" + field + "' no pertenece al dominio de VALIDAR.");
                continue;
            }
            if (!order_.count(field)) {
                errors_.push_back("Error semantico: no se puede validar '" + field + "' porque no existe en PEDIDO.");
                semanticChecks_.push_back("Fallo: '" + field + "' no fue declarado en PEDIDO.");
                continue;
            }
            if (field == "stock" && (!order_[field].isNumber || order_[field].number <= 0)) {
                errors_.push_back("Error semantico: stock debe ser un numero mayor que cero.");
                semanticChecks_.push_back("Fallo: stock debe sintetizar un numero mayor que cero.");
                continue;
            }
            if ((field == "direccion" || field == "pago") && order_[field].raw.empty()) {
                errors_.push_back("Error semantico: " + field + " no puede estar vacio.");
                semanticChecks_.push_back("Fallo: '" + field + "' sintetiza un texto vacio.");
                continue;
            }
            semanticChecks_.push_back("Correcto: VALIDAR " + field + " resolvio el simbolo y su valor.");
            logs_.push_back("Validacion aprobada: " + field);
        }

        for (const Action& action : actions_) {
            if (action.executed) logs_.push_back(action.kind + " -> " + action.target);
        }

        annotate(tree_, "global", "activo");
    }

private:
    std::vector<Token> tokens_;
    size_t current_ = 0;
    int nextNodeId_ = 1;
    std::map<std::string, OrderValue> order_;
    std::map<std::string, int> orderLines_;
    std::vector<Action> actions_;
    std::vector<std::string> validations_;
    std::vector<std::string> errors_;
    std::vector<std::string> logs_;
    SyntaxNode tree_;
    std::vector<SemanticAttribute> attributes_;
    std::vector<SymbolEntry> symbols_;
    std::vector<std::string> semanticChecks_;

    SyntaxNode makeNode(const std::string& symbol, const std::string& lexeme, int line) {
        return {nextNodeId_++, symbol, lexeme, line, {}};
    }

    bool check(TokenType type) const { return tokens_[current_].type == type; }
    bool checkLexeme(const std::string& lexeme) const { return tokens_[current_].lexeme == lexeme; }
    Token advance() { return tokens_[current_++]; }
    Token previous() const { return tokens_[current_ - 1]; }

    bool match(TokenType type) {
        if (!check(type)) return false;
        advance();
        return true;
    }

    bool matchReserved(const std::string& lexeme) {
        if (!check(TokenType::Reserved) || !checkLexeme(lexeme)) return false;
        advance();
        return true;
    }

    Token consume(TokenType type, const std::string& message) {
        if (check(type)) return advance();
        throw std::runtime_error(message + " cerca de linea " + std::to_string(tokens_[current_].line));
    }

    OrderValue consumeValue() {
        if (match(TokenType::String)) return {previous().lexeme, false, 0.0};
        if (match(TokenType::Number)) return {previous().lexeme, true, std::stod(previous().lexeme)};
        Token id = consume(TokenType::Identifier, "Se esperaba un valor STRING, NUMBER o IDENTIFIER");
        return {id.lexeme, false, 0.0};
    }

    SyntaxNode statement(bool conditional, bool active) {
        int line = tokens_[current_].line;
        try {
            if (matchReserved("PEDIDO")) return parseOrder(line);
            if (matchReserved("VALIDAR")) return parseValidation(line);
            if (matchReserved("SI")) return parseIf(line, active);
            if (matchReserved("ASIGNAR")) return parseAction("ASIGNAR", conditional, active, line);
            if (matchReserved("INICIAR")) return parseAction("INICIAR", conditional, active, line);
            if (matchReserved("FINALIZAR")) return parseAction("FINALIZAR", conditional, active, line);
            else {
                throw std::runtime_error("Instruccion no reconocida '" + tokens_[current_].lexeme +
                                         "' en linea " + std::to_string(tokens_[current_].line));
            }
        } catch (const std::exception& ex) {
            errors_.push_back(std::string("Error sintactico: ") + ex.what());
            synchronize();
            return makeNode("ErrorSintactico", ex.what(), line);
        }
    }

    SyntaxNode parseOrder(int line) {
        SyntaxNode node = makeNode("Pedido", "PEDIDO", line);
        consume(TokenType::LBrace, "Se esperaba '{' despues de PEDIDO");
        while (!check(TokenType::RBrace) && !check(TokenType::End)) {
            Token key = consume(TokenType::Identifier, "Se esperaba el nombre de una propiedad del pedido");
            consume(TokenType::Colon, "Se esperaba ':' despues de la propiedad '" + key.lexeme + "'");
            OrderValue value = consumeValue();
            order_[key.lexeme] = value;
            orderLines_[key.lexeme] = key.line;

            SyntaxNode property = makeNode("Propiedad", key.lexeme, key.line);
            property.children.push_back(makeNode(value.isNumber ? "Numero" : "Texto", value.raw, key.line));
            node.children.push_back(std::move(property));
        }
        consume(TokenType::RBrace, "Se esperaba '}' para cerrar PEDIDO");
        logs_.push_back("Pedido registrado");
        return node;
    }

    SyntaxNode parseValidation(int line) {
        Token field = consume(TokenType::Identifier, "Se esperaba el campo a validar");
        validations_.push_back(field.lexeme);
        SyntaxNode node = makeNode("Validacion", "VALIDAR", line);
        node.children.push_back(makeNode("Identificador", field.lexeme, field.line));
        return node;
    }

    SyntaxNode parseAction(const std::string& kind, bool conditional, bool active, int line) {
        Token target = consume(TokenType::Identifier, "Se esperaba el objetivo de la accion " + kind);
        actions_.push_back({kind, target.lexeme, conditional, active});
        SyntaxNode node = makeNode("Accion", kind, line);
        node.children.push_back(makeNode("Objetivo", target.lexeme, target.line));
        return node;
    }

    SyntaxNode parseIf(int line, bool parentActive) {
        Condition condition;
        Token left = consume(TokenType::Identifier, "Se esperaba variable en condicion SI");
        condition.left = left.lexeme;
        condition.line = left.line;
        Token op = consume(TokenType::Operator, "Se esperaba operador en condicion SI");
        condition.op = op.lexeme;
        condition.right = consumeValue();
        consume(TokenType::LBrace, "Se esperaba '{' despues de la condicion SI");

        bool result = evaluate(condition);
        logs_.push_back("Condicion SI " + condition.left + " " + condition.op + " " + condition.right.raw +
                        (result ? " aprobada" : " no aprobada"));

        SyntaxNode node = makeNode("Condicional", "SI", line);
        SyntaxNode conditionNode = makeNode("Condicion", condition.op, line);
        conditionNode.children.push_back(makeNode("Identificador", condition.left, left.line));
        conditionNode.children.push_back(makeNode("Operador", condition.op, op.line));
        conditionNode.children.push_back(makeNode(condition.right.isNumber ? "Numero" : "Texto",
                                                  condition.right.raw, op.line));
        node.children.push_back(std::move(conditionNode));
        SyntaxNode block = makeNode("Bloque", result ? "verdadero" : "falso", line);

        while (!check(TokenType::RBrace) && !check(TokenType::End)) {
            block.children.push_back(statement(true, parentActive && result));
        }
        consume(TokenType::RBrace, "Se esperaba '}' para cerrar SI");
        node.children.push_back(std::move(block));
        return node;
    }

    bool evaluate(const Condition& condition) {
        if (!order_.count(condition.left)) {
            errors_.push_back("Error semantico: la variable '" + condition.left + "' no existe en PEDIDO.");
            return false;
        }
        OrderValue left = order_[condition.left];
        if (left.isNumber && condition.right.isNumber) {
            if (condition.op == ">") return left.number > condition.right.number;
            if (condition.op == "<") return left.number < condition.right.number;
            if (condition.op == ">=") return left.number >= condition.right.number;
            if (condition.op == "<=") return left.number <= condition.right.number;
            if (condition.op == "==") return left.number == condition.right.number;
            if (condition.op == "!=") return left.number != condition.right.number;
        }
        if (condition.op == "==") return left.raw == condition.right.raw;
        if (condition.op == "!=") return left.raw != condition.right.raw;
        errors_.push_back("Error semantico: operador '" + condition.op + "' no valido para los tipos comparados.");
        return false;
    }

    void synchronize() {
        while (!check(TokenType::End)) {
            if (check(TokenType::Reserved) || check(TokenType::RBrace)) return;
            advance();
        }
    }

    SemanticAttribute annotate(const SyntaxNode& node, const std::string& scope,
                               const std::string& context) {
        std::string childScope = scope;
        std::string childContext = context;
        if (node.symbol == "Pedido") childScope = "global/PEDIDO";
        if (node.symbol == "Bloque") childContext = node.lexeme == "verdadero" ? "activo" : "inactivo";

        std::vector<SemanticAttribute> childAttributes;
        for (const SyntaxNode& child : node.children) {
            childAttributes.push_back(annotate(child, childScope, childContext));
        }

        SemanticAttribute attribute;
        attribute.nodeId = node.id;
        attribute.node = node.symbol;
        attribute.lexeme = node.lexeme;
        attribute.inheritedScope = scope;
        attribute.inheritedContext = context;
        attribute.synthesizedType = "estructura";
        attribute.synthesizedValue = std::to_string(node.children.size()) + " hijo(s)";
        attribute.rule = "La validez se sintetiza desde sus hijos.";

        for (const SemanticAttribute& child : childAttributes) attribute.valid = attribute.valid && child.valid;

        if (node.symbol == "Numero") {
            attribute.synthesizedType = "numero";
            attribute.synthesizedValue = node.lexeme;
            attribute.rule = "NUMBER.tipo := numero; NUMBER.valor := lexema";
        } else if (node.symbol == "Texto") {
            attribute.synthesizedType = "texto";
            attribute.synthesizedValue = node.lexeme;
            attribute.rule = "valor.tipo y valor.valor se sintetizan desde el terminal.";
        } else if (node.symbol == "Identificador") {
            auto found = order_.find(node.lexeme);
            attribute.valid = found != order_.end();
            attribute.synthesizedType = attribute.valid ? (found->second.isNumber ? "numero" : "texto") : "no definido";
            attribute.synthesizedValue = attribute.valid ? found->second.raw : "sin valor";
            attribute.rule = "IDENTIFICADOR usa el ambito heredado para resolver su simbolo.";
        } else if (node.symbol == "Propiedad" && !childAttributes.empty()) {
            attribute.synthesizedType = childAttributes[0].synthesizedType;
            attribute.synthesizedValue = childAttributes[0].synthesizedValue;
            attribute.rule = "propiedad.tipo/valor := valor.tipo/valor";
        } else if (node.symbol == "Condicion" && childAttributes.size() == 3) {
            attribute.synthesizedType = "booleano";
            attribute.synthesizedValue = childAttributes[0].synthesizedValue + " " + node.lexeme + " " +
                                         childAttributes[2].synthesizedValue;
            attribute.valid = childAttributes[0].valid &&
                              childAttributes[0].synthesizedType == childAttributes[2].synthesizedType;
            attribute.rule = "condicion.valida := tipos compatibles; resultado := comparar valores.";
        } else if (node.symbol == "Bloque") {
            attribute.synthesizedType = "secuencia";
            attribute.synthesizedValue = node.lexeme;
            attribute.rule = "El contexto de ejecucion se hereda a cada sentencia del bloque.";
        } else if (node.symbol == "ErrorSintactico") {
            attribute.valid = false;
            attribute.synthesizedType = "error";
            attribute.synthesizedValue = node.lexeme;
        }

        attributes_.push_back(attribute);
        return attribute;
    }
};

static std::string readFile(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("No se pudo abrir el archivo: " + path);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

static void printSyntaxNode(std::ostringstream& out, const SyntaxNode& node, int indent) {
    std::string padding(static_cast<size_t>(indent), ' ');
    out << padding << "{\"id\": " << node.id
        << ", \"symbol\": \"" << jsonEscape(node.symbol)
        << "\", \"lexeme\": \"" << jsonEscape(node.lexeme)
        << "\", \"line\": " << node.line << ", \"children\": [";
    if (!node.children.empty()) out << "\n";
    for (size_t i = 0; i < node.children.size(); ++i) {
        printSyntaxNode(out, node.children[i], indent + 2);
        out << (i + 1 < node.children.size() ? ",\n" : "\n");
    }
    if (!node.children.empty()) out << padding;
    out << "]}";
}

static std::string buildJson(const std::vector<Token>& tokens, const Parser& parser) {
    std::ostringstream out;
    bool success = parser.errors().empty();
    out << "{\n";
    out << "  \"success\": " << (success ? "true" : "false") << ",\n";

    out << "  \"tokens\": [\n";
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (tokens[i].type == TokenType::End) continue;
        out << "    {\"type\": \"" << tokenTypeName(tokens[i].type)
            << "\", \"lexeme\": \"" << jsonEscape(tokens[i].lexeme)
            << "\", \"line\": " << tokens[i].line
            << ", \"column\": " << tokens[i].column << "}";
        bool last = i + 1 >= tokens.size() || tokens[i + 1].type == TokenType::End;
        out << (last ? "\n" : ",\n");
    }
    out << "  ],\n";

    out << "  \"order\": {";
    size_t count = 0;
    for (const auto& item : parser.order()) {
        out << (count++ ? ", " : "") << "\"" << jsonEscape(item.first) << "\": ";
        if (item.second.isNumber) out << item.second.raw;
        else out << "\"" << jsonEscape(item.second.raw) << "\"";
    }
    out << "},\n";

    out << "  \"syntax\": {\n";
    out << "    \"parser\": \"descendente recursivo LL(1)\",\n";
    out << "    \"tree\": ";
    printSyntaxNode(out, parser.tree(), 4);
    out << "\n  },\n";

    out << "  \"semantic\": {\n";
    out << "    \"symbols\": [";
    for (size_t i = 0; i < parser.symbols().size(); ++i) {
        const SymbolEntry& symbol = parser.symbols()[i];
        out << (i ? ", " : "")
            << "{\"name\": \"" << jsonEscape(symbol.name)
            << "\", \"type\": \"" << jsonEscape(symbol.type)
            << "\", \"value\": \"" << jsonEscape(symbol.value)
            << "\", \"line\": " << symbol.line << "}";
    }
    out << "],\n";

    out << "    \"attributes\": [\n";
    for (size_t i = 0; i < parser.attributes().size(); ++i) {
        const SemanticAttribute& attribute = parser.attributes()[i];
        out << "      {\"node_id\": " << attribute.nodeId
            << ", \"node\": \"" << jsonEscape(attribute.node)
            << "\", \"lexeme\": \"" << jsonEscape(attribute.lexeme)
            << "\", \"inherited\": {\"scope\": \"" << jsonEscape(attribute.inheritedScope)
            << "\", \"context\": \"" << jsonEscape(attribute.inheritedContext)
            << "\"}, \"synthesized\": {\"type\": \"" << jsonEscape(attribute.synthesizedType)
            << "\", \"value\": \"" << jsonEscape(attribute.synthesizedValue)
            << "\", \"valid\": " << (attribute.valid ? "true" : "false")
            << "}, \"rule\": \"" << jsonEscape(attribute.rule) << "\"}";
        out << (i + 1 < parser.attributes().size() ? ",\n" : "\n");
    }
    out << "    ],\n";

    out << "    \"checks\": [";
    for (size_t i = 0; i < parser.semanticChecks().size(); ++i) {
        out << (i ? ", " : "") << "\"" << jsonEscape(parser.semanticChecks()[i]) << "\"";
    }
    out << "]\n";
    out << "  },\n";

    out << "  \"logs\": [";
    for (size_t i = 0; i < parser.logs().size(); ++i) {
        out << (i ? ", " : "") << "\"" << jsonEscape(parser.logs()[i]) << "\"";
    }
    out << "],\n";

    out << "  \"errors\": [";
    for (size_t i = 0; i < parser.errors().size(); ++i) {
        out << (i ? ", " : "") << "\"" << jsonEscape(parser.errors()[i]) << "\"";
    }
    out << "]\n";
    out << "}\n";
    return out.str();
}

static std::string buildErrorJson(const std::string& message) {
    std::ostringstream out;
    out << "{\n";
    out << "  \"success\": false,\n";
    out << "  \"tokens\": [],\n";
    out << "  \"order\": {},\n";
    out << "  \"syntax\": {\"parser\": \"descendente recursivo LL(1)\", \"tree\": null},\n";
    out << "  \"semantic\": {\"symbols\": [], \"attributes\": [], \"checks\": []},\n";
    out << "  \"logs\": [],\n";
    out << "  \"errors\": [\"" << jsonEscape(message) << "\"]\n";
    out << "}\n";
    return out.str();
}

// Traduccion final del compilador: persiste el JSON generado (exito o error)
// en un archivo de salida, ademas de imprimirlo por stdout para que web/app.py
// siga funcionando exactamente igual que antes.
static void saveJsonFile(const std::string& jsonText) {
    namespace fs = std::filesystem;
    try {
        fs::path outputDir = "output";
        fs::create_directories(outputDir);

        fs::path outputFile = outputDir / "last_compile.json";
        std::ofstream outFile(outputFile, std::ios::binary);
        if (!outFile) {
            std::cerr << "Aviso: no se pudo escribir output/last_compile.json\n";
            return;
        }
        outFile << jsonText;
    } catch (const std::exception& ex) {
        std::cerr << "Aviso: no se pudo exportar el JSON a archivo (" << ex.what() << ")\n";
    }
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Uso: delivery_compiler <archivo.dsl>\n";
        return 1;
    }

    try {
        std::string source = readFile(argv[1]);
        Lexer lexer(source);
        std::vector<Token> tokens = lexer.scan();
        Parser parser(tokens);
        parser.parse();
        parser.semanticAnalysis();

        std::string jsonText = buildJson(tokens, parser);
        saveJsonFile(jsonText);
        std::cout << jsonText;

        return parser.errors().empty() ? 0 : 2;
    } catch (const std::exception& ex) {
        std::string jsonText = buildErrorJson(ex.what());
        saveJsonFile(jsonText);
        std::cout << jsonText;
        return 1;
    }
}

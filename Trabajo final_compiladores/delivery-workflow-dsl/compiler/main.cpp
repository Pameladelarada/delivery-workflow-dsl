#include <cctype>
#include <cstdlib>
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
};

struct Action {
    std::string kind;
    std::string target;
    bool conditional = false;
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
    explicit Parser(std::vector<Token> tokens) : tokens_(std::move(tokens)) {}

    void parse() {
        while (!check(TokenType::End)) {
            statement(false);
        }
    }

    const std::map<std::string, OrderValue>& order() const { return order_; }
    const std::vector<Action>& actions() const { return actions_; }
    const std::vector<std::string>& validations() const { return validations_; }
    const std::vector<std::string>& errors() const { return errors_; }
    const std::vector<std::string>& logs() const { return logs_; }

    void semanticAnalysis() {
        std::set<std::string> allowedValidations = {"stock", "direccion", "pago", "cliente", "producto", "total"};

        if (order_.empty()) {
            errors_.push_back("Error semantico: el programa debe definir un bloque PEDIDO.");
        }

        for (const std::string& field : validations_) {
            if (!allowedValidations.count(field)) {
                errors_.push_back("Error semantico: VALIDAR " + field + " no pertenece al dominio permitido.");
                continue;
            }
            if (!order_.count(field)) {
                errors_.push_back("Error semantico: no se puede validar '" + field + "' porque no existe en PEDIDO.");
                continue;
            }
            if (field == "stock" && (!order_[field].isNumber || order_[field].number <= 0)) {
                errors_.push_back("Error semantico: stock debe ser un numero mayor que cero.");
            }
            if ((field == "direccion" || field == "pago") && order_[field].raw.empty()) {
                errors_.push_back("Error semantico: " + field + " no puede estar vacio.");
            }
            logs_.push_back("Validacion aprobada: " + field);
        }

        for (const Action& action : actions_) {
            logs_.push_back(action.kind + " -> " + action.target);
        }
    }

private:
    std::vector<Token> tokens_;
    size_t current_ = 0;
    std::map<std::string, OrderValue> order_;
    std::vector<Action> actions_;
    std::vector<std::string> validations_;
    std::vector<std::string> errors_;
    std::vector<std::string> logs_;

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

    Token consumeIdentifierLike(const std::string& message) {
        if (check(TokenType::Identifier) || check(TokenType::Reserved)) return advance();
        throw std::runtime_error(message + " cerca de linea " + std::to_string(tokens_[current_].line));
    }

    OrderValue consumeValue() {
        if (match(TokenType::String)) return {previous().lexeme, false, 0.0};
        if (match(TokenType::Number)) return {previous().lexeme, true, std::stod(previous().lexeme)};
        Token id = consumeIdentifierLike("Se esperaba un valor");
        return {id.lexeme, false, 0.0};
    }

    void statement(bool conditional) {
        try {
            if (matchReserved("PEDIDO")) parseOrder();
            else if (matchReserved("VALIDAR")) parseValidation();
            else if (matchReserved("SI")) parseIf();
            else if (matchReserved("ASIGNAR")) parseAction("ASIGNAR", conditional);
            else if (matchReserved("INICIAR")) parseAction("INICIAR", conditional);
            else if (matchReserved("FINALIZAR")) parseAction("FINALIZAR", conditional);
            else {
                throw std::runtime_error("Instruccion no reconocida '" + tokens_[current_].lexeme +
                                         "' en linea " + std::to_string(tokens_[current_].line));
            }
        } catch (const std::exception& ex) {
            errors_.push_back(std::string("Error sintactico: ") + ex.what());
            synchronize();
        }
    }

    void parseOrder() {
        consume(TokenType::LBrace, "Se esperaba '{' despues de PEDIDO");
        while (!check(TokenType::RBrace) && !check(TokenType::End)) {
            Token key = consumeIdentifierLike("Se esperaba el nombre de una propiedad del pedido");
            consume(TokenType::Colon, "Se esperaba ':' despues de la propiedad '" + key.lexeme + "'");
            OrderValue value = consumeValue();
            order_[key.lexeme] = value;
        }
        consume(TokenType::RBrace, "Se esperaba '}' para cerrar PEDIDO");
        logs_.push_back("Pedido registrado");
    }

    void parseValidation() {
        Token field = consumeIdentifierLike("Se esperaba el campo a validar");
        validations_.push_back(field.lexeme);
    }

    void parseAction(const std::string& kind, bool conditional) {
        Token target = consumeIdentifierLike("Se esperaba el objetivo de la accion " + kind);
        actions_.push_back({kind, target.lexeme, conditional});
    }

    void parseIf() {
        Condition condition;
        Token left = consumeIdentifierLike("Se esperaba variable en condicion SI");
        condition.left = left.lexeme;
        Token op = consume(TokenType::Operator, "Se esperaba operador en condicion SI");
        condition.op = op.lexeme;
        condition.right = consumeValue();
        consume(TokenType::LBrace, "Se esperaba '{' despues de la condicion SI");

        bool result = evaluate(condition);
        logs_.push_back("Condicion SI " + condition.left + " " + condition.op + " " + condition.right.raw +
                        (result ? " aprobada" : " no aprobada"));

        while (!check(TokenType::RBrace) && !check(TokenType::End)) {
            if (result) statement(true);
            else skipStatement();
        }
        consume(TokenType::RBrace, "Se esperaba '}' para cerrar SI");
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

    void skipStatement() {
        if (matchReserved("SI")) {
            while (!check(TokenType::LBrace) && !check(TokenType::End)) advance();
            if (match(TokenType::LBrace)) {
                int depth = 1;
                while (depth > 0 && !check(TokenType::End)) {
                    if (match(TokenType::LBrace)) depth++;
                    else if (match(TokenType::RBrace)) depth--;
                    else advance();
                }
            }
            return;
        }
        while (!check(TokenType::Reserved) && !check(TokenType::RBrace) && !check(TokenType::End)) advance();
        if (check(TokenType::Reserved)) {
            advance();
            while (!check(TokenType::Reserved) && !check(TokenType::RBrace) && !check(TokenType::End)) advance();
        }
    }

    void synchronize() {
        while (!check(TokenType::End)) {
            if (check(TokenType::Reserved) || check(TokenType::RBrace)) return;
            advance();
        }
    }
};

static std::string readFile(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("No se pudo abrir el archivo: " + path);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

static void printJson(const std::vector<Token>& tokens, const Parser& parser) {
    bool success = parser.errors().empty();
    std::cout << "{\n";
    std::cout << "  \"success\": " << (success ? "true" : "false") << ",\n";

    std::cout << "  \"tokens\": [\n";
    for (size_t i = 0; i < tokens.size(); ++i) {
        if (tokens[i].type == TokenType::End) continue;
        std::cout << "    {\"type\": \"" << tokenTypeName(tokens[i].type)
                  << "\", \"lexeme\": \"" << jsonEscape(tokens[i].lexeme)
                  << "\", \"line\": " << tokens[i].line
                  << ", \"column\": " << tokens[i].column << "}";
        bool last = i + 1 >= tokens.size() || tokens[i + 1].type == TokenType::End;
        std::cout << (last ? "\n" : ",\n");
    }
    std::cout << "  ],\n";

    std::cout << "  \"order\": {";
    size_t count = 0;
    for (const auto& item : parser.order()) {
        std::cout << (count++ ? ", " : "") << "\"" << jsonEscape(item.first) << "\": ";
        if (item.second.isNumber) std::cout << item.second.raw;
        else std::cout << "\"" << jsonEscape(item.second.raw) << "\"";
    }
    std::cout << "},\n";

    std::cout << "  \"logs\": [";
    for (size_t i = 0; i < parser.logs().size(); ++i) {
        std::cout << (i ? ", " : "") << "\"" << jsonEscape(parser.logs()[i]) << "\"";
    }
    std::cout << "],\n";

    std::cout << "  \"errors\": [";
    for (size_t i = 0; i < parser.errors().size(); ++i) {
        std::cout << (i ? ", " : "") << "\"" << jsonEscape(parser.errors()[i]) << "\"";
    }
    std::cout << "]\n";
    std::cout << "}\n";
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
        printJson(tokens, parser);
        return parser.errors().empty() ? 0 : 2;
    } catch (const std::exception& ex) {
        std::cout << "{\n";
        std::cout << "  \"success\": false,\n";
        std::cout << "  \"tokens\": [],\n";
        std::cout << "  \"order\": {},\n";
        std::cout << "  \"logs\": [],\n";
        std::cout << "  \"errors\": [\"" << jsonEscape(ex.what()) << "\"]\n";
        std::cout << "}\n";
        return 1;
    }
}

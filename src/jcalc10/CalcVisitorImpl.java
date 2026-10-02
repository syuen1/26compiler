package calc2;

import java.util.List;

public class CalcVisitorImpl implements CalcVisitor {
  public Object visit(SimpleNode node, Object data) {
    return null;
  }

  public Object visit(ASTRoot node, Object data) {
    return node.jjtGetChild(0).jjtAccept(this, null);
  }

  public Object visit(ASTExpr node, Object data) {
    return node.jjtGetChild(0).jjtAccept(this, null);
  }

  public Object visit(ASTAddExpr node, Object data) {
    List<Token> ops = (List<Token>) node.jjtGetValue();
        int size = node.jjtGetNumChildren();
        Double x = (Double) node.jjtGetChild(0).jjtAccept(this, null);
        for (int i = 1; i < size; i++) {
            switch (ops.get(i - 1).toString()) {
            case "+":
                x = x + (Double) node.jjtGetChild(i).jjtAccept(this, null);
                break;
            case "-":
                x = x - (Double) node.jjtGetChild(i).jjtAccept(this, null);
                break;
            }
        }
        return x;
  }

  public Object visit(ASTMulExpr node, Object data) {
        List<Token> ops = (List<Token>) node.jjtGetValue();

        int size = node.jjtGetNumChildren();
        Double x = (Double) node.jjtGetChild(0).jjtAccept(this, null);
        for (int i = 1; i < size; i++) {
            switch (ops.get(i - 1).toString()) {
            case "*":
                x = x * (Double) node.jjtGetChild(i).jjtAccept(this, null);
                break;
            case "/":
                x = x / (Double) node.jjtGetChild(i).jjtAccept(this, null);
                break;
            case "%":
                x = x % (Double) node.jjtGetChild(i).jjtAccept(this, null);
                break;
            }
        }
        return x;
    }

  public Object visit(ASTUnaryExpr node, Object data) {
    return node.jjtGetChild(0).jjtAccept(this, null);
  }

  public Object visit(ASTDecimal node, Object data) {
    return Double.valueOf(((Token) node.jjtGetValue()).toString());
  }
}

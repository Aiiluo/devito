from devito.dimension import LoweredDimension
from devito.ir.iet import FindNodes, Expression
from devito.logger import yask_warning as warning

from devito.yask import nfac

__all__ = ['yaskizer']


def yaskizer(root, yc_soln):
    """
    Convert a SymPy expression into a YASK abstract syntax tree and create the
    necessay YASK grids.

    :param root: The outermost space :class:`Iteration` defining an offloadable
                 loop nest.
    :param yc_soln: The YASK compiler solution to which the new YASK grids are
                    attached.
    """
    mapper = {}

    for i in FindNodes(Expression).visit(root):
        node = handle(i.expr, yc_soln, mapper)

    return mapper


def handle(expr, yc_soln, mapper):

    def nary2binary(args, op):
        r = handle(args[0], yc_soln, mapper)
        return r if len(args) == 1 else op(r, nary2binary(args[1:], op))

    if expr.is_Integer:
        return nfac.new_const_number_node(int(expr))
    elif expr.is_Float:
        return nfac.new_const_number_node(float(expr))
    elif expr.is_Rational:
        a, b = expr.as_numer_denom()
        return nfac.new_const_number_node(float(a)/float(b))
    elif expr.is_Symbol:
        function = expr.base.function
        if function.is_Constant:
            if function not in mapper:
                mapper[function] = yc_soln.new_grid(function.name, [])
            return mapper[function].new_relative_grid_point([])
        else:
            # A DSE-generated temporary, which must have already been
            # encountered as a LHS of a previous expression
            assert function in mapper
            return mapper[function]
    elif expr.is_Indexed:
        function = expr.base.function
        if function not in mapper:
            if function.is_TimeFunction:
                dimensions = [nfac.new_step_index(function.indices[0].name)]
                dimensions += [nfac.new_domain_index(i.name)
                               for i in function.indices[1:]]
            else:
                dimensions = [nfac.new_domain_index(i.name)
                              for i in function.indices]
            mapper[function] = yc_soln.new_grid(function.name, dimensions)
        indices = [int((i.origin if isinstance(i, LoweredDimension) else i) - j)
                   for i, j in zip(expr.indices, function.indices)]
        return mapper[function].new_relative_grid_point(indices)
    elif expr.is_Add:
        return nary2binary(expr.args, nfac.new_add_node)
    elif expr.is_Mul:
        return nary2binary(expr.args, nfac.new_multiply_node)
    elif expr.is_Pow:
        base, exp = expr.as_base_exp()
        if not exp.is_integer:
            warning("non-integer powers unsupported in Devito-YASK translation")
            raise NotImplementedError

        if int(exp) < 0:
            num, den = expr.as_numer_denom()
            return nfac.new_divide_node(handle(num, yc_soln, mapper),
                                        handle(den, yc_soln, mapper))
        elif int(exp) >= 1:
            return nary2binary([base] * exp, nfac.new_multiply_node)
        else:
            warning("0-power found in Devito-YASK translation? setting to 1")
            return nfac.new_const_number_node(1)
    elif expr.is_Equality:
        if expr.lhs.is_Symbol:
            function = expr.lhs.base.function
            assert function not in mapper
            mapper[function] = handle(expr.rhs, yc_soln, mapper)
        else:
            return nfac.new_equation_node(*[handle(i, yc_soln, mapper)
                                            for i in expr.args])
    else:
        warning("Missing handler in Devito-YASK translation")
        raise NotImplementedError

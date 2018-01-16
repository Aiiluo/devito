from collections import OrderedDict

import sympy

from devito.ir.support import Interval, DataSpace, IterationSpace, Stencil
from devito.symbolics import dimension_sort, indexify

__all__ = ['Eq']


class EqMixin(object):

    """
    A mixin providing operations common to all :mod:`ir` equation types.
    """

    @property
    def is_Scalar(self):
        return self.lhs.is_Symbol

    @property
    def is_Tensor(self):
        return self.lhs.is_Indexed


class Eq(sympy.Eq, EqMixin):

    """
    Eq(expr, subs=None)

    A SymPy equation with associated iteration and data spaces.

    The data space is an object of type :class:`DataSpace`. It represents the
    data points accessed by the equation along each :class:`Dimension`. The
    :class:`Dimension`s are extracted directly from the equation.

    The iteration space is an object of type :class:`IterationSpace`. It
    represents the iteration points along each :class:`Dimension` that the
    equation may traverse with the guarantee that no out-of-bounds accesses
    will be performed.
    """

    def __new__(cls, *args, **kwargs):
        # Parse input
        if len(args) == 1:
            expr = input_expr = args[0]
            assert isinstance(expr, sympy.Eq)
        elif len(args) == 2:
            # Reconstructing from existing Eq. E.g., we end up here after xreplace
            expr = super(Eq, cls).__new__(cls, *args, evaluate=False)
            stamp = kwargs.get('stamp')
            assert isinstance(stamp, Eq)
            expr.is_Increment = stamp.is_Increment
            expr.dspace = stamp.dspace
            expr.ispace = stamp.ispace
            return expr
        else:
            raise ValueError("Cannot construct Eq from args=%s "
                             "and kwargs=%s" % (str(args), str(kwargs)))

        expr = super(Eq, cls).__new__(cls, expr.lhs, expr.rhs, evaluate=False)
        expr.is_Increment = getattr(input_expr, 'is_Increment', False)

        # Get the accessed data points
        stencil = Stencil(expr)

        # Well-defined dimension ordering
        ordering = dimension_sort(expr, key=lambda i: not i.is_Time)

        # Split actual Intervals (the data spaces) from the "derived" iterators,
        # to build an IterationSpace
        iterators = OrderedDict()
        for i in ordering:
            if i.is_Derived:
                iterators.setdefault(i.parent, []).append(stencil.entry(i))
            else:
                iterators.setdefault(i, [])
        intervals = []
        for k, v in iterators.items():
            offs = set.union(set(stencil.get(k)), *[i.ofs for i in v])
            intervals.append(Interval(k, min(offs), max(offs)))

        # Data space and Iteration space
        expr.dspace = DataSpace(intervals)
        expr.ispace = IterationSpace([Interval(i.dim, 0, 0) for i in intervals],
                                     iterators)

        return expr

    def xreplace(self, rules):
        return Eq(self.lhs.xreplace(rules), self.rhs.xreplace(rules), stamp=self)

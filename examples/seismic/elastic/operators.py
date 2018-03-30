from sympy import solve, Symbol

from devito import Eq, Operator, Function, TimeFunction, centered, left, right
from devito.logger import error
from examples.seismic import PointSource, Receiver


def staggered_diff(f, dim, order, stagger=centered):
    """
    Utility function to generate staggered derivatives
    """
    diff = dim.spacing
    if stagger == left:
        off = -.5
    elif stagger == right:
        off = .5
    else:
        off = 0.
    idx = [(dim + int(i+.5+off)*diff) for i in range(-int(order / 2), int(order / 2))]
    return f.diff(dim).as_finite_difference(idx, x0=dim + off*dim.spacing)

def ForwardOperator(model, source, receiver, space_order=4,
                    save=False, kernel='OT2', **kwargs):
    """
    Constructor method for the forward modelling operator in an acoustic media

    :param model: :class:`Model` object containing the physical parameters
    :param source: :class:`PointData` object containing the source geometry
    :param receiver: :class:`PointData` object containing the acquisition geometry
    :param space_order: Space discretization order
    :param save: Saving flag, True saves all time steps, False only the three
    """
    vp, vs, rho = model.vp, model.vs, model.rho
    s = model.grid.stepping_dim.spacing
    x, z = model.grid.dimensions
    cp2 = vp*vp
    cs2 = vs*vs
    ro = 1/rho

    mu = cs2*ro
    l = (cp2*ro - 2*mu)

    # Create symbols for forward wavefield, source and receivers
    vx = TimeFunction(name='vx', grid=model.grid, staggered=(0, 1, 0),
                      save=source.nt if save else None,
                      time_order=2, space_order=space_order)
    vz = TimeFunction(name='vz', grid=model.grid, staggered=(0, 0, 1),
                      save=source.nt if save else None,
                      time_order=2, space_order=space_order)
    txx = TimeFunction(name='txx', grid=model.grid,
                      save=source.nt if save else None,
                      time_order=2, space_order=space_order)
    tzz = TimeFunction(name='tzz', grid=model.grid,
                      save=source.nt if save else None,
                      time_order=2, space_order=space_order)
    txz = TimeFunction(name='txz', grid=model.grid, staggered=(0, 1, 1),
                      save=source.nt if save else None,
                      time_order=2, space_order=space_order)
    # Source and receivers
    src = PointSource(name='src', grid=model.grid, ntime=source.nt,
                      npoint=source.npoint)
    rec1 = Receiver(name='rec1', grid=model.grid, ntime=receiver.nt,
                   npoint=receiver.npoint)
    rec2 = Receiver(name='rec2', grid=model.grid, ntime=receiver.nt,
                   npoint=receiver.npoint)
    # Stencils
    u_vx = Eq(vx.forward, vx - s*ro*(staggered_diff(txx, dim=x, order=space_order, stagger=left)
                                    + staggered_diff(txz, dim=z, order=space_order, stagger=right)))

    u_vz = Eq(vz.forward, vz - ro*s*(staggered_diff(txz, dim=x, order=space_order, stagger=right)
                                    + staggered_diff(tzz, dim=z, order=space_order, stagger=left)))

    u_txx = Eq(txx.forward, txx - (l+2*mu)*s * staggered_diff(vx.forward, dim=x, order=space_order, stagger=right)
                                -  l*s       * staggered_diff(vz.forward, dim=z, order=space_order, stagger=right))
    u_tzz = Eq(tzz.forward, tzz - (l+2*mu)*s * staggered_diff(vz.forward, dim=z, order=space_order, stagger=right)
                                -  l*s       * staggered_diff(vx.forward, dim=x, order=space_order, stagger=right))

    u_txz = Eq(txz.forward, txz - mu*s * (staggered_diff(vx.forward, dim=z, order=space_order, stagger=left)
                                         + staggered_diff(vz.forward, dim=x, order=space_order, stagger=left)))

    # The source injection term
    src_xx = src.inject(field=txx.forward, expr=src, offset=model.nbpml)
    src_zz = src.inject(field=tzz.forward, expr=src, offset=model.nbpml)

    # Create interpolation expression for receivers
    rec_term1 = rec1.interpolate(expr=vx, offset=model.nbpml)
    rec_term2 = rec2.interpolate(expr=vz, offset=model.nbpml)
    # Substitute spacing terms to reduce flops
    return Operator([u_vx, u_vz, u_txx, u_tzz, u_txz] + src_xx + src_zz + rec_term1 + rec_term2, subs=model.spacing_map,
                    name='Forward', **kwargs)

from sympy import *

from devito.dimension import x, y, z, t, time
from devito.finite_difference import centered, first_derivative, left
from devito.interfaces import DenseData, TimeData
from devito.operator import Operator
from devito.stencilkernel import StencilKernel


def ForwardOperator(model, u, v, src, rec, data, time_order=2,
                    spc_order=4, save=False, u_ini=None, legacy=True,
                    **kwargs):
    """
    Constructor method for the forward modelling operator in an acoustic media

    :param model: :class:`Model` object containing the physical parameters
    :param src: None ot IShot() (not currently supported properly)
    :param data: IShot() object containing the acquisition geometry and field data
    :param: time_order: Time discretization order
    :param: spc_order: Space discretization order
    :param: u_ini : wavefield at the three first time step for non-zero initial condition
    """
    nt, nrec = data.shape
    nt, nsrc = src.shape
    dt = model.critical_dt
    m, damp = model.m, model.damp
    epsilon, delta, theta, phi = model.epsilon, model.delta, model.theta, model.phi
    parm = [m, damp, u, v]
    parm += [p for p in [epsilon, delta, theta, phi] if isinstance(p, DenseData)]

    s, h = symbols('s h')

    spc_brd = spc_order/2

    ang0 = cos(theta)
    ang1 = sin(theta)
    ang2 = cos(phi)
    ang3 = sin(phi)
    if len(model.shape) == 3:
        # Derive stencil from symbolic equation
        Gyp = (ang3 * u.dx - ang2 * u.dyr)
        Gyy = (first_derivative(Gyp * ang3,
                                dim=x, side=centered, order=spc_brd) -
               first_derivative(Gyp * ang2,
                                dim=y, side=left, order=spc_brd))
        Gyp2 = (ang3 * u.dxr - ang2 * u.dy)
        Gyy2 = (first_derivative(Gyp2 * ang3,
                                 dim=x, side=left, order=spc_brd) -
                first_derivative(Gyp2 * ang2,
                                 dim=y, side=centered, order=spc_brd))

        Gxp = (ang0 * ang2 * u.dx + ang0 * ang3 * u.dyr - ang1 * u.dzr)
        Gzr = (ang1 * ang2 * v.dx + ang1 * ang3 * v.dyr + ang0 * v.dzr)
        Gxx = (first_derivative(Gxp * ang0 * ang2,
                                dim=x, side=centered, order=spc_brd) +
               first_derivative(Gxp * ang0 * ang3,
                                dim=y, side=left, order=spc_brd) -
               first_derivative(Gxp * ang1,
                                dim=z, side=left, order=spc_brd))
        Gzz = (first_derivative(Gzr * ang1 * ang2,
                                dim=x, side=centered, order=spc_brd) +
               first_derivative(Gzr * ang1 * ang3,
                                dim=y, side=left, order=spc_brd) +
               first_derivative(Gzr * ang0,
                                dim=z, side=left, order=spc_brd))
        Gxp2 = (ang0 * ang2 * u.dxr + ang0 * ang3 * u.dy - ang1 * u.dz)
        Gzr2 = (ang1 * ang2 * v.dxr + ang1 * ang3 * v.dy + ang0 * v.dz)
        Gxx2 = (first_derivative(Gxp2 * ang0 * ang2,
                                 dim=x, side=left, order=spc_brd) +
                first_derivative(Gxp2 * ang0 * ang3,
                                 dim=y, side=centered, order=spc_brd) -
                first_derivative(Gxp2 * ang1,
                                 dim=z, side=centered, order=spc_brd))
        Gzz2 = (first_derivative(Gzr2 * ang1 * ang2,
                                 dim=x, side=left, order=spc_brd) +
                first_derivative(Gzr2 * ang1 * ang3,
                                 dim=y, side=centered, order=spc_brd) +
                first_derivative(Gzr2 * ang0,
                                 dim=z, side=centered, order=spc_brd))
        Hp = (.5*Gxx + .5*Gxx2 + .5 * Gyy + .5*Gyy2)
        Hzr = (.5*Gzz + .5 * Gzz2)

    else:
        Gx1p = (ang0 * u.dxr - ang1 * u.dy)
        Gz1r = (ang1 * v.dxr + ang0 * v.dy)
        Gxx1 = (first_derivative(Gx1p * ang0, dim=x,
                                 side=left, order=spc_brd) -
                first_derivative(Gx1p * ang1, dim=y,
                                 side=centered, order=spc_brd))
        Gzz1 = (first_derivative(Gz1r * ang1, dim=x,
                                 side=left, order=spc_brd) +
                first_derivative(Gz1r * ang0, dim=y,
                                 side=centered, order=spc_brd))
        Gx2p = (ang0 * u.dx - ang1 * u.dyr)
        Gz2r = (ang1 * v.dx + ang0 * v.dyr)
        Gxx2 = (first_derivative(Gx2p * ang0, dim=x,
                                 side=centered, order=spc_brd) -
                first_derivative(Gx2p * ang1, dim=y,
                                 side=left, order=spc_brd))
        Gzz2 = (first_derivative(Gz2r * ang1, dim=x,
                                 side=centered, order=spc_brd) +
                first_derivative(Gz2r * ang0, dim=y,
                                 side=left, order=spc_brd))

        Hp = (.5 * Gxx1 + .5 * Gxx2)
        Hzr = (.5 * Gzz1 + .5 * Gzz2)

    stencilp = 1.0 / (2.0 * m + s * damp) * \
        (4.0 * m * u + (s * damp - 2.0 * m) *
         u.backward + 2.0 * s**2 * (epsilon * Hp + delta * Hzr))
    stencilr = 1.0 / (2.0 * m + s * damp) * \
        (4.0 * m * v + (s * damp - 2.0 * m) *
         v.backward + 2.0 * s**2 * (delta * Hp + Hzr))

    # Add substitutions for spacing (temporal and spatial)
    subs = {s: dt, h: model.get_spacing()}
    first_stencil = Eq(u.forward, stencilp)
    second_stencil = Eq(v.forward, stencilr)
    stencils = [first_stencil, second_stencil]

    if legacy:
        kwargs.pop('dle', None)

        op = Operator(nt, model.shape_domain, stencils=stencils, subs=[subs, subs],
                      spc_border=spc_order, time_order=time_order,
                      forward=True, dtype=m.dtype, input_params=parm,
                      **kwargs)

        # Insert source and receiver terms post-hoc
        op.input_params += [src, src.coordinates, rec, rec.coordinates]
        op.output_params += [v, rec]
        op.propagator.time_loop_stencils_a = (src.add(m, u) + src.add(m, v) +
                                              rec.read2(u, v))
        op.propagator.add_devito_param(src)
        op.propagator.add_devito_param(src.coordinates)
        op.propagator.add_devito_param(rec)
        op.propagator.add_devito_param(rec.coordinates)

    else:
        dse = kwargs.get('dse', 'advanced')
        dle = kwargs.get('dle', 'advanced')
        compiler = kwargs.get('compiler', None)

        stencils += src.point2grid(u, m, u_t=t, p_t=time)
        stencils += src.point2grid(v, m, u_t=t, p_t=time)
        stencils += [Eq(rec, rec.grid2point(u) + rec.grid2point(v))]

        # TODO: The following time-index hackery is a legacy hangover
        # from the Operator/Propagator structure and is used here for
        # backward compatibiliy. We need re-examine this apporach carefully!

        # Shift time indices so that LHS writes into t only,
        # eg. u[t+2] = u[t+1] + u[t]  -> u[t] = u[t-1] + u[t-2]
        stencils = [e.subs(t, t + solve(e.lhs.args[0], t)[0])
                    if isinstance(e.lhs, TimeData) else e
                    for e in stencils]
        # Apply time substitutions as per legacy approach
        time_subs = {t + 2: t + 1, t: t + 2, t - 2: t, t - 1: t + 1, t + 1: t}
        subs.update(time_subs)

        op = StencilKernel(stencils=stencils, subs=subs, dse=dse, dle=dle)

    return op


def ForwardOperatorDB(model, u, v, src, rec, data, time_order=2,
                      spc_order=4, save=False, u_ini=None, legacy=True,
                      **kwargs):
    """
    Constructor method for the forward modelling operator in an acoustic media

    :param model: :class:`Model` object containing the physical parameters
    :param src: None ot IShot() (not currently supported properly)
    :param data: IShot() object containing the acquisition geometry and field data
    :param: time_order: Time discretization order
    :param: spc_order: Space discretization order
    :param: u_ini : wavefield at the three first time step for non-zero initial condition
    """
    nt, nrec = data.shape
    nt, nsrc = src.shape
    dt = model.critical_dt
    m, damp = model.m, model.damp
    epsilon, delta, theta, phi = model.epsilon, model.delta, model.theta, model.phi
    parm = [m, damp, u, v]
    parm += [p for p in [epsilon, delta, theta, phi] if isinstance(p, DenseData)]

    s, h = symbols('s h')

    spc_brd = spc_order/2

    ang0 = cos(theta)
    ang1 = sin(theta)
    ang2 = cos(phi)
    ang3 = sin(phi)

    R_mat = [[ang0 * ang2, ang0*ang3, -ang1],
             [-ang3, ang2, 0],
             [ang1*ang2, ang1*ang3, ang0]]
    dims = [x, y, z]

    if len(model.shape) == 3:
        # Derive stencil from symbolic equation
        H1 = 0
        H2 = 0
        for k in range(3):
            for l in range(3):
                coeff1 = (R_mat[0][k] * R_mat[0][l] + R_mat[1][k] * R_mat[1][l])
                coeff2 = R_mat[2][k]*R_mat[2][l]
                for j in range(3):
                    H1 += coeff1 * (first_derivative(first_derivative((R_mat[0][k] * R_mat[0][j] + R_mat[1][k] * R_mat[1][j])*u +
                                                                      (R_mat[2][k]*R_mat[2][j])*v,
                                                                      dim=dims[l], side=centered, order=spc_brd),
                                                     dim=dims[j], side=centered, order=spc_brd))

                    H2 += coeff2 * (first_derivative(first_derivative((R_mat[0][k] * R_mat[0][j] + R_mat[1][k] * R_mat[1][j])*u +
                                                                      (R_mat[2][k]*R_mat[2][j])*v,
                                                                      dim=dims[l], side=centered, order=spc_brd),
                                                     dim=dims[j], side=centered, order=spc_brd))

    else:
        raise NotImplementedError

    stencilp = 1.0 / (2.0 * m + s * damp) * \
        (4.0 * m * u + (s * damp - 2.0 * m) *
         u.backward + 2.0 * s**2 * (epsilon * H1 + delta * H2))
    stencilr = 1.0 / (2.0 * m + s * damp) * \
        (4.0 * m * v + (s * damp - 2.0 * m) *
         v.backward + 2.0 * s**2 * (delta * H1 + H2))
    # Add substitutions for spacing (temporal and spatial)
    subs = {s: dt, h: model.get_spacing()}
    first_stencil = Eq(u.forward, stencilp)
    second_stencil = Eq(v.forward, stencilr)
    stencils = [first_stencil, second_stencil]

    if legacy:
        kwargs.pop('dle', None)

        op = Operator(nt, model.shape_domain, stencils=stencils, subs=[subs, subs],
                      spc_border=spc_order, time_order=time_order,
                      forward=True, dtype=m.dtype, input_params=parm,
                      **kwargs)

        # Insert source and receiver terms post-hoc
        op.input_params += [src, src.coordinates, rec, rec.coordinates]
        op.output_params += [v, rec]
        op.propagator.time_loop_stencils_a = (src.add(m, u) + src.add(m, v) +
                                              rec.read2(u, v))
        op.propagator.add_devito_param(src)
        op.propagator.add_devito_param(src.coordinates)
        op.propagator.add_devito_param(rec)
        op.propagator.add_devito_param(rec.coordinates)

    else:
        dse = kwargs.get('dse', 'advanced')
        dle = kwargs.get('dle', 'advanced')
        compiler = kwargs.get('compiler', None)

        stencils += src.point2grid(u, m, u_t=t, p_t=time)
        stencils += src.point2grid(v, m, u_t=t, p_t=time)
        stencils += [Eq(rec, rec.grid2point(u) + rec.grid2point(v))]

        # TODO: The following time-index hackery is a legacy hangover
        # from the Operator/Propagator structure and is used here for
        # backward compatibiliy. We need re-examine this apporach carefully!

        # Shift time indices so that LHS writes into t only,
        # eg. u[t+2] = u[t+1] + u[t]  -> u[t] = u[t-1] + u[t-2]
        stencils = [e.subs(t, t + solve(e.lhs.args[0], t)[0])
                    if isinstance(e.lhs, TimeData) else e
                    for e in stencils]
        # Apply time substitutions as per legacy approach
        time_subs = {t + 2: t + 1, t: t + 2, t - 2: t, t - 1: t + 1, t + 1: t}
        subs.update(time_subs)

        op = StencilKernel(stencils=stencils, subs=subs, dse=dse, dle=dle)

    return op
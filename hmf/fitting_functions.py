"""
A module defining several mass function fits.

Each fit is taken from the literature. If there are others out there that are not
listed here, please advise via GitHub.
"""

import numpy as np
from scipy.interpolate import InterpolatedUnivariateSpline as _spline
import scipy.special as sp
from . import cosmo as csm
from . import _framework
from copy import copy
from . import _utils



class SimDetails(object):
    """
    A description of a suite of simulations used to define a mass function.

    The parameters given should describe the simulations used to *define*
    the mass function in the given study, not all simulations run in the study
    against which the fit was compared.

    Several parametes take either scalar or list values. These should be provided
    consistently, so that a single value refers to all simulations, and all lists
    are the same length.

    Parameters
    ----------
    L : list of floats
        The boxsizes of the simulations [Mpc/h]

    N : list of ints
        The number of particles in the simulations

    halo_finder_type : str
        Either "FoF" or "SO"

    omegam : float or list of floats
        Matter density used.

    sigma_8 : float or list of floats
        Normalisation used.

    halo_overdensity : float
        Halo overdensity used (linking length in case of FoF definition)

    halo_finder : str, optional
        Name of halo finding code.

    softening : list of floats, optional
        Softening length [kpc/h]

    transfer : str or list of str, optional
        An identifier for the transfer function calculator used.

    z_start : float or list of floats, optional
        The starting redshift of the simulation

    z_meas : float or 2-tuple, optional
        Either the redshift of HMF measurement, or (min,max).

    ICS : str or list of str, optional
        How the ICS were generated, either "1LPT" or "2LPT"

    nmin : int, optional
        The minimum number of particles per halo for haloes used in the fit.

    hmf_analysis_notes : str, optional
        A description of any pertinent details about how the HMF was
        analysed in the study.

    other_cosmo : dict, optional
        Other cosmological parameters of interest.
    """

    def __init__(self, L, N, halo_finder_type,
                 omegam, sigma_8, halo_overdensity, halo_finder=None,
                 softening=None, transfer=None, z_start=None,
                 z_meas=None, ICS=None,nmin=None,
                 hmf_analysis_notes="", other_cosmo={}):

        # Possible multi-sims
        self.L = np.atleast_1d(L)
        self.N = np.atleast_1d(N)
        self.omegam = np.atleast_1d(omegam)
        self.sigma_8 = np.atleast_1d(sigma_8)
        self.transfer = np.atleast_1d(transfer)
        self.z_start = np.atleast_1d(z_start)
        self.softening = np.atleast_1d(softening)
        self.ICS = np.atleast_1d(ICS)

        self.z_meas = z_meas
        self.halo_finder_type = halo_finder_type
        self.halo_overdensity = halo_overdensity
        self.halo_finder = halo_finder
        self.hmf_analysis_notes = hmf_analysis_notes
        self.nmin = nmin

        self.other_cosmo = other_cosmo

        # Derived
        self.V = self.L**3
        try:
            self.mp = self.omegam*2.7755e11*self.V/self.N
        except:
            self.mp = None
        try:
            self.mmin = self.mp*self.nmin
        except:
            self.mmin = None


def _makedoc(pdocs, lname, sname, eq, ref):
    return \
        r"""
    %s mass function fit.

    For details on attributes, see documentation for :class:`FittingFunction`.
    """%lname + pdocs + \
        r"""
    Notes
    -----
    The %s [1]_ form is:

    .. math:: f_{\rm %s}(\sigma) = %s

    References
    ----------
    .. [1] %s
    """%(lname, sname, eq, ref)


class FittingFunction(_framework.Component):
    r"""
    Base-class for a halo mass function fit.

    This class should not be called directly, rather use a subclass which is
    specific to a certain fitting formula. The only method necessary to define
    for any subclass is `fsigma`, as well as a dictionary of default parameters
    as a class variable `_defaults`. Model parameters defined here are accessed
    through the :attr:`params` instance attribute (and may be overridden at
    instantiation by the user). A subclass may optionally
    define a :attr:`cutmask` property, to override the default behaviour of
    returning True for the whole range.

    In addition, several class attributes, `req_*`, identify the required
    arguments for a given subclass. These must be set accordingly.

    Examples
    --------
    The following would be an example of defining the Sheth-Tormen mass
    function (which is already included), showing the basic idea of subclassing
    this class:

    >>> class SMT(FittingFunction):
    >>>     # Subclass requirements
    >>>     req_sigma = False
    >>>     req_z     = False
    >>>
    >>>     # Default parameters
    >>>     _defaults = {"a":0.707, "p":0.3, "A":0.3222}
    >>>
    >>>     @property
    >>>     def fsigma(self):
    >>>        A = self.params['A']
    >>>        a = self.params["a"]
    >>>        p = self.params['p']
    >>>
    >>>        return (A * np.sqrt(2.0 * a / np.pi) * self.nu * np.exp(-(a * self.nu2) / 2.0)
    >>>               * (1 + (1.0 / (a * self.nu2)) ** p))

    In that example, we did not specify :attr:`cutmask`.
    """
    _pdocs = \
        """

    Parameters
    ----------
    nu2  : array_like
        A vector of peak-heights, :math:`\delta_c^2/\sigma^2` corresponding to `m`

    m   : array_like, optional
        A vector of halo masses [units M_sun/h]. Only necessary if :attr:`req_mass`
        is True. Typically provides limits of applicability. Must correspond to
        `nu2`.

    z   : float, optional
        The redshift. Only required if :attr:`req_z` is True, in which case the default
        is 0.

    n_eff : array_like, optional
        The effective spectral index at `m`. Only required if :attr:`req_neff` is True.
        
    delta_halo : float, optional
        The overdensity of the halo w.r.t. the mean density of the universe.
        Only required if :attr:`req_dhalo` is True, in which case the default is 200.0

    cosmo : :class:`hmf.cosmo.Cosmology` instance, optional
        A cosmology. Default is the default provided by the :class:`cosmo.Cosmology`
        class. Either `omegam_z` or `cosmo` is required if :attr:`req_omz` is True.
        If both are passed, omegam_z takes precedence.

    omegam_z : float, optional
        A value for the mean matter density at the given redshift `z`. Either
        `omegam_z` or `cosmo` is required if :attr:`req_omz` is True.
        If both are passed, omegam_z takes precedence.

    \*\*model_parameters : unpacked-dictionary
        These parameters are model-specific. For any model, list the available
        parameters (and their defaults) using ``<model>._defaults``

    """
    __doc__ += _pdocs
    _defaults = {}

    # Subclass requirements
    req_omz = False
    "Whether `omegam_z` is required for this subclass"
    req_neff = False
    "Whether `n_eff` is required for this subclass"
    req_sigma = True
    "Whether `sigma` (via `delta_c`) is required for this subclass"
    req_z = True
    "Whether `z` is required for this subclass"
    req_dhalo = False
    "Whether `delta_halo` is required for this subclass"
    req_mass = False
    "Whether `m` is required for this subclass"

    sim_definition = None
    "Details of the defining simulation, subclass of ``SimDetails``"

    def __init__(self, nu2, m=None, z=0, n_eff=None,
                 delta_halo=200, cosmo=None, omegam_z=None, delta_c=1.686,
                 **model_parameters):

        super(FittingFunction, self).__init__(**model_parameters)

        # Save instance variables
        self.nu2 = nu2

        if self.req_mass:
            assert m is not None
            self.m = m

        if self.req_dhalo:
            self.delta_halo = delta_halo

        if self.req_z:
            self.z = z

        if self.req_neff:
            assert n_eff is not None
            self.n_eff = n_eff

        # Derived variables
        self.nu = np.sqrt(nu2)
        if self.req_sigma:
            self.sigma = delta_c/self.nu
            self.lnsigma = -np.log(self.sigma)

        if self.req_omz:
            if omegam_z is None:
                if cosmo is None:
                    cosmo = csm.Cosmology()
                self.omegam_z = cosmo.cosmo.Om(self.z)
            else:
                self.omegam_z = omegam_z

    @property
    def cutmask(self):
        r"""
        A logical mask array specifying which elements of :attr:`fsigma` are within
        the fitted range.
        """
        return np.ones(len(self.nu2), dtype=bool)

    @property
    def fsigma(self):
        r"""
        The function :math:`f(\sigma)\equiv\nu f(\nu)`.
        """
        pass


class PS(FittingFunction):
    # Subclass requirements
    req_sigma = False
    req_z = False

    _eq = r"\sqrt{\frac{2}{\pi}}\nu\exp(-0.5\nu^2)"
    _ref = r"""Press, W. H., Schechter, P., 1974. ApJ 187, 425-438. http://adsabs.harvard.edu/full/1974ApJ...187..425P"""

    __doc__ = _makedoc(FittingFunction._pdocs, "Press-Schechter", "PS", _eq, _ref)

    @property
    def fsigma(self):
        return np.sqrt(2.0/np.pi)*self.nu*np.exp(-0.5*self.nu2)


class SMT(FittingFunction):
    # Subclass requirements
    req_sigma = False
    req_z = False

    _eq = r"A\sqrt{2a/\pi}\nu\exp(-a\nu^2/2)(1+(a\nu^2)^{-p})"
    _ref = r"""Sheth, R. K., Mo, H. J., Tormen, G., May 2001. MNRAS 323 (1), 1-12. http://doi.wiley.com/10.1046/j.1365-8711.2001.04006.x"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Sheth-Mo-Tormen", "SMT", _eq, _ref)

    _defaults = {"a": 0.707, "p": 0.3, "A": 0.3222}

    sim_definition = SimDetails(L=[84.5, 141.3],
                                N=[256**3, 256**3],
                                halo_finder_type="SO",
                                omegam=0.3,
                                sigma_8=0.9,
                                halo_overdensity=178.0,
                                halo_finder=None,
                                softening=30.0,
                                transfer="BondEfs",
                                z_start=30.0,
                                z_meas=0.0,
                                ICS=None,
                                nmin=None,
                                hmf_analysis_notes="No details are given about measurement of HMF. ",
                                other_cosmo={"omegav": 0.7,
                                             "h": 0.7,
                                             "n": 1})

    @property
    def fsigma(self):
        A = self.norm()
        a = self.params["a"]
        p = self.params['p']

        vfv = A*np.sqrt(2.0*a/np.pi)*self.nu*np.exp(-(a*self.nu2)/2.0) \
              *(1 + (1.0/(a*self.nu2))**p)

        return vfv

    def norm(self):
        if self.params["A"] is not None:
            return self.params['A']
        else:
            p = self.params['p']
            return 1./(1 + 2**-p*sp.gamma(0.5 - p)/sp.gamma(0.5))


class ST(SMT):
    """
    Alias of :class:`SMT`
    """
    pass


class Jenkins(FittingFunction):
    # Subclass requirements
    req_z = False

    _eq = r"A\exp\left(-\left|\ln\sigma^{-1}+b\right|^c\right)"
    _ref = r"""Jenkins, A. R., et al., Feb. 2001. MNRAS 321 (2), 372-384. http://doi.wiley.com/10.1046/j.1365-8711.2001.04029.x"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Jenkins", "Jenkins", _eq, _ref)
    _defaults = {"A": 0.315, "b": 0.61, "c": 3.8}

    sim_definition = SimDetails(L=[84.5, 141.3, 479, 3000],
                                N=[256**3, 256**3, 134217728, 1000**3],
                                halo_finder_type="FoF",
                                omegam=0.3,
                                sigma_8=0.9,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=30.0,
                                transfer="BondEfs",
                                z_start=30.0,
                                z_meas=(0.0, 5.0),
                                ICS=None,
                                nmin=20,
                                hmf_analysis_notes="""
                                Many cosmologies used. Preferentially listed LCDM here.
                                Fit involves "smoothing" and deconvolving HMF.""",
                                other_cosmo={"omegav": 0.7,
                                             "h": 0.7,
                                             "n": 1})

    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -1.2, self.lnsigma < 1.05)

    @property
    def fsigma(self):
        A = self.params["A"]
        b = self.params["b"]
        c = self.params['c']
        return A*np.exp(-np.abs(self.lnsigma + b)**c)


class Warren(FittingFunction):
    # Subclass requirements
    req_z = False
    req_mass = True

    _eq = r"A\left[\left(\frac{e}{\sigma}\right)^b + c\right]\exp\left(\frac{d}{\sigma^2}\right)"
    _ref = r"""Warren, M. S., et al., Aug. 2006. ApJ 646 (2), 881-885. http://adsabs.harvard.edu/abs/2006ApJ...646..881W"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Warren", "Warren", _eq, _ref)

    _defaults = {"A": 0.7234, "b": 1.625, "c": 0.2538, "d": 1.1982, "e": 1}

    uncertainties = {"A": 0.0073, "a": 0.028, "b": 0.0051, "c": 0.0075}
    sim_definition = SimDetails(L=[96, 135, 192, 272, 384, 543, 768, 1086, 1536, 2172, 2583, 3072],
                                N=1024**3,
                                halo_finder_type="FoF",
                                omegam=0.3,
                                sigma_8=0.9,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[2.1, 134.0/31., 192/31., 272/31., 384/31., 543/31.,
                                           768/31., 1086/31., 1536/31., 2172/31., 2583/31., 98],
                                transfer="CMBFAST",
                                z_start=None,
                                z_meas=(0.0, 5.0),
                                ICS="1LPT",
                                nmin=400,
                                hmf_analysis_notes="FOF N-Correction applied. Fit uses ML of Poisson counts.",
                                other_cosmo={"omegav": 0.7,
                                             "omegab": 0.04,
                                             "h": 0.7,
                                             "n": 1})

    @property
    def fsigma(self):
        A = self.params["A"]
        b = self.params["b"]
        c = self.params['c']
        d = self.params['d']
        e = self.params['e']

        return A*((e/self.sigma)**b + c)*np.exp(-d/self.sigma**2)

    @property
    def cutmask(self):
        return np.logical_and(self.m > 1e10, self.m < 1e15)


class Reed03(SMT):
    # Subclass requirements
    req_sigma = True

    _eq = r"f_{\rm SMT}(\sigma)\exp\left(-\frac{c}{\sigma \cosh^5(2\sigma)}\right)"
    _ref = r"""Reed, D., et al., Dec. 2003. MNRAS 346 (2), 565-572. http://adsabs.harvard.edu/abs/2003MNRAS.346..565R"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Reed03", "R03", _eq, _ref)

    _defaults = {"a": 0.707, "p": 0.3, "A": 0.3222, "c": 0.7}

    sim_definition = SimDetails(L=50.0,
                                N=432**3,
                                halo_finder_type="FoF",
                                omegam=0.3,
                                sigma_8=1.0,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=5.0,
                                transfer="BBKS",
                                z_start=[69,139],
                                z_meas=(0.0, 15.0),
                                ICS="1LPT",
                                nmin=64,
                                hmf_analysis_notes="HMF seems to be purely binned.",
                                other_cosmo={"omegav": 0.7,
                                             "omegab": 0.04,
                                             "h":None,
                                             "n": None})
    @property
    def fsigma(self):
        vfv = super(Reed03, self).fsigma
        return vfv*np.exp(-self.params['c']/(self.sigma*np.cosh(2.0*self.sigma)**5))

    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -1.7, self.lnsigma < 0.9)


class Reed07(FittingFunction):
    req_neff = True
    req_z = False

    _eq = r"A\sqrt{2a/\pi}\left[1+(\frac{1}{a\nu^2})^p+0.6G_1+0.4G_2\right]\nu\exp\left(-ca\nu^2/2-\frac{0.03\nu^{0.6}}{(n_{\rm eff}+3)^2}\right)"
    _ref = """Reed, D. S., et al., Jan. 2007. MNRAS 374 (1), 2-15. http://adsabs.harvard.edu/abs/2007MNRAS.374....2R"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Reed07", "R07", _eq, _ref)

    _defaults = {"A": 0.3222, "p": 0.3, "c": 1.08, "a": 0.764}

    sim_definition = SimDetails(L=[1.0,2.5,2.5,2.5,2.5,4.64,11.6,20,50,100,500,1340,3000],
                                N=[400**3,1000**3,1000**3,500**3,200**3,400**3,1000**3,400**3,1000**3,900**3,2160**3,1448**3,1000**3],
                                halo_finder_type="FoF",
                                omegam=0.3,
                                sigma_8=0.9,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[0.125,0.125,0.125,0.25,0.625,0.58,0.58,2.5,2.4,2.4,5.0,20,100],
                                transfer="CMBFAST",
                                z_start=[299,299,299,299,299,249,249,249,299,149,127,63,35],
                                z_meas=[10,10,30,10,10,10,10,10,10,10,0,0,0],
                                ICS="1LPT",
                                nmin=100,
                                hmf_analysis_notes="Finite volume corrections applied.",
                                other_cosmo={"omegav": 0.7,
                                             "omegab":None,
                                             "h":0.7,
                                             "n": 1.0})
    @property
    def fsigma(self):
        G_1 = np.exp(-(self.lnsigma - 0.4)**2/(2*0.6**2))
        G_2 = np.exp(-(self.lnsigma - 0.75)**2/(2*0.2**2))

        c = self.params['c']
        a = self.params['a']/self.params['c']
        A = self.params['A']
        p = self.params['p']

        return A*np.sqrt(2.0*a/np.pi)* \
               (1.0 + (1.0/(a*self.nu**2))**p + 0.6*G_1 + 0.4*G_2)*self.nu* \
               np.exp(-c*a*self.nu**2/2.0 - 0.03*self.nu**0.6/(self.n_eff + 3)**2)

    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -0.5, self.lnsigma < 1.2)


class Peacock(FittingFunction):
    req_z = False
    req_mass = True

    _eq = r"\nu\exp(-c\nu^2)(2cd\nu+ba\nu^{b-1})/d^2"
    _ref = """Peacock, J. A., Aug. 2007. MNRAS 379 (3), 1067-1074. http://adsabs.harvard.edu/abs/2007MNRAS.379.1067P"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Peacock", "Pck", _eq, _ref)
    _defaults = {"a": 1.529, "b": 0.704, 'c': 0.412}

    sim_definition = copy(Warren.sim_definition)
    sim_definition.hmf_analysis_notes = "Fit directly to Warren+2006 fit."

    @property
    def fsigma(self):
        a = self.params['a']
        b = self.params['b']
        c = self.params['c']

        d = 1 + a*self.nu**b
        return self.nu*np.exp(-c*self.nu2)*(2*c*d*self.nu + b*a*self.nu**(b - 1))/d**2

    @property
    def cutmask(self):
        return np.logical_and(self.m < 1e10, self.m > 1e15)


class Angulo(FittingFunction):
    req_mass = True
    _ref = """Angulo, R. E., et al., 2012. arXiv:1203.3216v1"""
    _eq = r"$A \left[\left(\frac{d}{\sigma}\right)^b + 1 \right] \exp(-c/\sigma^2)$"
    __doc__ = _makedoc(FittingFunction._pdocs, "Angulo", "Ang", _eq, _ref)
    _defaults = {"A": 0.201, "b": 1.7, "c": 1.172, "d": 2.08}

    sim_definition = SimDetails(L=3000.0,
                                N=6720**3,
                                halo_finder_type="FoF",
                                omegam=0.25,
                                sigma_8=0.9,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=13.79,
                                transfer="CAMB",
                                z_start=63,
                                z_meas=0,
                                ICS="2LPT",
                                nmin=20,
                                hmf_analysis_notes="No corrections seem to be applied; no special techniques.",
                                other_cosmo={"omegav": 0.75,
                                             "omegab":0.045,
                                             "h":0.73,
                                             "n": 1.0})
    @property
    def fsigma(self):
        A = self.params['A']
        b = self.params['b']
        c = self.params['c']
        d = self.params['d']

        return A * ((d/self.sigma)**b+1) * np.exp(-c/self.sigma**2)

    @property
    def cutmask(self):
        return np.logical_and(self.m > 1e8, self.m < 1e16)


class AnguloBound(Angulo):
    __doc__ = Angulo.__doc__
    _defaults = {"A": 0.265, "b": 1.9, "c": 1.4, "d": 1.675}


class Watson_FoF(Warren):
    req_mass = False

    _ref = """Watson, W. A., et al., MNRAS, 2013. http://adsabs.harvard.edu/abs/2013MNRAS.433.1230W """
    __doc__ = _makedoc(FittingFunction._pdocs, "Watson FoF", "WatF", Warren._eq, _ref)
    _defaults = {"A": 0.282, "b": 2.163, "c": 1, "d": 1.21, "e": 1.406}

    sim_definition = SimDetails(L=[11.4,20,114,425,1000,3200,6000],
                                N=[3072**3,5488**3,3072**3,5488**3,3456**3,4000**3,6000**3],
                                halo_finder_type="FoF",
                                omegam=0.27,
                                sigma_8=0.8,
                                halo_overdensity=0.2,
                                halo_finder="GADGET3",
                                softening=[0.18,0.18,1.86,3.87,14.47,40.0,50.0],
                                transfer="CAMB",
                                z_start=[300,300,300,300,150,120,100],
                                z_meas=(0,30),
                                ICS="1LPT",
                                nmin=1000,
                                hmf_analysis_notes="Warren FOF correction applied. Finite-box correction applied.",
                                other_cosmo={"omegav": 0.73,
                                             "omegab":0.044,
                                             "h":0.7,
                                             "n": 0.96})
    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -0.55, self.lnsigma < 1.31)


class Watson(FittingFunction):
    req_cosmo = True
    req_dhalo = True
    req_omz = True

    _ref = """Watson, W. A., et al., MNRAS, 2013. http://adsabs.harvard.edu/abs/2013MNRAS.433.1230W """
    _eq = r"\Gamma A \left((\frac{\beta}{\sigma}^\alpha+1\right)\exp(-\gamma/\sigma^2)"
    __doc__ = _makedoc(FittingFunction._pdocs, "Watson", "WatS", _eq, Watson_FoF._ref)

    sim_definition = copy(Watson_FoF.sim_definition)
    sim_definition.halo_finder_type = "SO"
    sim_definition.halo_finder = "AHF"
    sim_definition.halo_overdensity = 178.0

    _defaults = {"C_a": 0.023, "d_a": 0.456, "d_b": 0.139, "p": 0.072, "q": 2.13,
                 "A_0": 0.194, "alpha_0": 1.805, "beta_0": 2.267, "gamma_0": 1.287,
                 "z_hi": 6, "A_hi": 0.563, "alpha_hi": 0.874, "beta_hi": 3.810, "gamma_hi": 1.453,
                 "A_a": 1.097, "A_b": 3.216, "A_c": 0.074,
                 "alpha_a": 3.136, "alpha_b": 3.058, "alpha_c": 2.349,
                 "beta_a": 5.907, "beta_b": 3.599, "beta_c": 2.344,
                 "gamma_z": 1.318}

    def gamma(self):
        """
        Calculate :math:`\Gamma` for the Watson fit.
        """
        C = np.exp(self.params["C_a"]*(self.delta_halo/178 - 1))
        d = -self.params["d_a"]*self.omegam_z - self.params["d_b"]
        p = self.params["p"]
        q = self.params['q']

        return C*(self.delta_halo/178)**d*np.exp(p*(1 - self.delta_halo/178)/self.sigma**q)

    @property
    def fsigma(self):
        if self.z == 0:
            A = self.params["A_0"]
            alpha = self.params["alpha_0"]
            beta = self.params["beta_0"]
            gamma = self.params["gamma_0"]
        elif self.z >= self.params['z_hi']:
            A = self.params["A_hi"]
            alpha = self.params["alpha_hi"]
            beta = self.params["beta_hi"]
            gamma = self.params["gamma_hi"]
        else:
            omz = self.omegam_z
            A = omz*(self.params["A_a"]*(1 + self.z)**(-self.params["A_b"]) + self.params["A_c"])
            alpha = omz*(self.params["alpha_a"]*(1 + self.z)**(-self.params["alpha_b"]) + self.params["alpha_c"])
            beta = omz*(self.params["beta_a"]*(1 + self.z)**(-self.params["beta_b"]) + self.params["beta_c"])
            gamma = self.params["gamma_z"]

        return self.gamma()*A*((beta/self.sigma)**alpha + 1)* \
               np.exp(-gamma/self.sigma**2)

    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -0.55, self.lnsigma < 1.05)


class Crocce(Warren):
    req_z = True

    _ref = """Crocce, M., et al. MNRAS 403 (3), 1353-1367. http://doi.wiley.com/10.1111/j.1365-2966.2009.16194.x"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Crocce", "Cro", Warren._eq, _ref)
    _defaults = {"A_a": 0.58, "A_b": 0.13,
                 "b_a": 1.37, "b_b": 0.15,
                 "c_a": 0.3, "c_b": 0.084,
                 "d_a": 1.036, "d_b": 0.024,
                 "e": 1}

    sim_definition = SimDetails(L=[7680,3072,4500,768,384,179],
                                N=[2048**3,2048**3,1200**3,1024**3,1024**3,1024**3],
                                halo_finder_type="FoF",
                                omegam=0.25,
                                sigma_8=0.8,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[50,50,100,50,50,50],
                                transfer="CAMB",
                                z_start=[150,50,50,50,50,50],
                                z_meas=(0,1),
                                ICS=["1LPT","1LPT","2LPT","2LPT","2LPT","2LPT"],
                                nmin=200,
                                hmf_analysis_notes="Warren FOF correction applied.",
                                other_cosmo={"omegav": 0.75,
                                             "omegab":0.044,
                                             "h":0.7,
                                             "n": 0.95})

    def __init__(self, *args, **kwargs):
        super(Crocce, self).__init__(*args, **kwargs)

        self.params["A"] = self.params["A_a"]*(1 + self.z)**(-self.params["A_b"])
        self.params['b'] = self.params["b_a"]*(1 + self.z)**(-self.params["b_b"])
        self.params['c'] = self.params["c_a"]*(1 + self.z)**(-self.params["c_b"])
        self.params['d'] = self.params["d_a"]*(1 + self.z)**(-self.params["d_b"])

    @property
    def cutmask(self):
        return np.logical_and(self.m > 10**10.5, self.m < 10**15.5)


class Courtin(SMT):
    req_sigma = True
    _ref = """Courtin, J., et al., Oct. 2010. MNRAS 1931. http://doi.wiley.com/10.1111/j.1365-2966.2010.17573.x"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Courtin", "Ctn", SMT._eq, _ref)
    _defaults = {"A": 0.348, "a": 0.695, "p": 0.1}

    sim_definition = SimDetails(L=[162,648,1296],
                                N=[512**3,512**3,512**3],
                                halo_finder_type="FoF",
                                omegam=0.26,
                                sigma_8=0.79,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[2.47,19.78,39.55],
                                transfer="CAMB",
                                z_start=[93,56,41],
                                z_meas=0,
                                ICS="1LPT",
                                nmin=200,
                                hmf_analysis_notes="Many systematic effects tested but not applied.",
                                other_cosmo={"omegav": 0.74,
                                             "omegab":0.044,
                                             "h":0.72,
                                             "n": 0.963})
    @property
    def cutmask(self):
        return np.logical_and(self.lnsigma > -0.8, self.lnsigma < 0.7)


class Bhattacharya(SMT):
    req_z = True
    req_mass = True

    _eq = r"f_{\rm SMT}(\sigma) (\nu\sqrt{a})^{q-1}"
    _ref = """Bhattacharya, S., et al., May 2011. ApJ 732 (2), 122. http://labs.adsabs.harvard.edu/ui/abs/2011ApJ...732..122B"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Bhattacharya", "Btc", _eq, _ref)
    _defaults = {"A_a": 0.333, "A_b": 0.11, "a_a": 0.788, "a_b": 0.01, "p": 0.807, "q": 1.795}

    sim_definition = SimDetails(L=[1000*0.72,1736*0.72,2778*0.72,178*0.72,1300*0.72],
                                N=[1500**3,1200**3,1024**3,512**3,1024**3],
                                halo_finder_type="FoF",
                                omegam=None, #what is lower case omega??
                                sigma_8=0.8,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[24,51,97,14,50],
                                transfer="CAMB",
                                z_start=[75,100,100,211,211],
                                z_meas=(0,2),
                                ICS=["2LPT","2LPT","2LPT","1LPT","1LPT"],
                                nmin=400,
                                hmf_analysis_notes="Finite force correction. FOF Correction. Finite volume correction.",
                                other_cosmo={"omegav": 0.74,
                                             "omegab":None, ## uses lower case omega without definition
                                             "h":0.72,
                                             "n": 0.97})

    def __init__(self, **kwargs):
        super(Bhattacharya, self).__init__(**kwargs)
        self.params["A"] = self.params["A_a"]*(1 + self.z)**-self.params["A_b"]
        self.params["a"] = self.params["a_a"]*(1 + self.z)**-self.params["a_b"]

    @property
    def fsigma(self):
        """
        Calculate :math:`f(\sigma)` for Bhattacharya form.

        Bhattacharya, S., et al., May 2011. ApJ 732 (2), 122.
        http://labs.adsabs.harvard.edu/ui/abs/2011ApJ...732..122B

        .. note:: valid for :math:`10^{11.8}M_\odot < M <10^{15.5}M_\odot`

        Returns
        -------
        vfv : array_like, len=len(pert.M)
            The function :math:`f(\sigma)\equiv\nu f(\nu)` defined on ``pert.M``
        """
        vfv = super(Bhattacharya, self).fsigma
        return vfv*(np.sqrt(self.params['a']) * self.nu)**(self.params['q'] - 1)

    @property
    def cutmask(self):
        return np.logical_and(self.m > 6*10**11,
                              self.m < 3*10**15)


class Tinker08(FittingFunction):
    req_z = True
    req_dhalo = True

    _eq = r"A\left(\frac{\sigma}{b}^{-a}+1\right)\exp(-c/\sigma^2)"
    _ref = """Tinker, J., et al., 2008. ApJ 688, 709-728. http://iopscience.iop.org/0004-637X/688/2/709"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Tinker08", "Tkr", _eq, _ref)

    sim_definition = SimDetails(L=[768,384,271,192,96,1280,500,250,120,80,1000,500,500,500,384,384,120,80],
                                N=[1024**3,1024**3,1024**3,1024**3,1024**3,640**3,1024**3,512**3,512**3,512**3,1024**3,512**3,512**3,512**3,1024**3,1024**3,1024**3,512**3],
                                halo_finder_type="SO",
                                omegam=[0.3,0.3,0.3,0.3,0.3,0.27,0.3,0.3,0.3,0.3,0.27,0.24,0.24,0.24,0.26,0.2,0.27,0.23],
                                sigma_8=[0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.9,0.79,0.75,0.75,0.8,0.75,0.9,0.79,0.75],
                                halo_overdensity=200.0,
                                halo_finder=None,
                                softening=[25,14,10,4.9,1.4,120,15,7.6,1.8,1.2,30,15,15,15,14,14,0.9,1.2],
                                transfer=None,
                                z_start=[40,48,51,54,65,49,40,49,49,49,60,40,40,40,35,42,100,49],
                                z_meas=(0,2.5),
                                ICS="1LPT",
                                nmin=None,
                                hmf_analysis_notes="No corrections applied.",
                                other_cosmo={"omegav":[0.7,0.7,0.7,0.7,0.7,0.73,0.7,0.7,0.7,0.7,0.73,0.76,0.76,0.76,0.74,0.8,0.73,0.77],
                                             "omegab":[0.04,0.04,0.04,0.04,0.04,0.04,0.045,0.04,0.04,0.04,0.044,0.042,0.042,0.042,0.042,0.044,0.04,0.044,0.04],
                                             "h":[0.7,0.7,0.7,0.7,0.7,0.7,0.7,0.7,0.7,0.7,0.7,0.73,0.73,0.73,0.71,0.7,0.7,0.73],
                                             "n": [1,1,1,1,1,1,1,1,1,1,0.95,0.95,0.95,0.95,0.94,1,0.95,0.95]})


    _defaults = {  # -- A
        "A_200": 1.858659e-01,
        "A_300": 1.995973e-01,
        "A_400": 2.115659e-01,
        "A_600": 2.184113e-01,
        "A_800": 2.480968e-01,
        "A_1200": 2.546053e-01,
        "A_1600": 2.600000e-01,
        "A_2400": 2.600000e-01,
        "A_3200": 2.600000e-01,
        # -- a
        "a_200": 1.466904,
        "a_300": 1.521782,
        "a_400": 1.559186,
        "a_600": 1.614585,
        "a_800": 1.869936,
        "a_1200": 2.128056,
        "a_1600": 2.301275,
        "a_2400": 2.529241,
        "a_3200": 2.661983,
        # --- b
        "b_200": 2.571104,
        "b_300": 2.254217,
        "b_400": 2.048674,
        "b_600": 1.869559,
        "b_800": 1.588649,
        "b_1200": 1.507134,
        "b_1600": 1.464374,
        "b_2400": 1.436827,
        "b_3200": 1.405210,
        # --- c
        "c_200": 1.193958,
        "c_300": 1.270316,
        "c_400": 1.335191,
        "c_600": 1.446266,
        "c_800": 1.581345,
        "c_1200": 1.795050,
        "c_1600": 1.965613,
        "c_2400": 2.237466,
        "c_3200": 2.439729,
        # -- others
        "A_exp": 0.14, "a_exp": 0.06}

    delta_virs = np.array([200, 300, 400, 600, 800, 1200, 1600, 2400, 3200])

    def __init__(self, **model_parameters):
        super(Tinker08, self).__init__(**model_parameters)

        if self.delta_halo not in self.delta_virs:
            A_array = np.array([self.params["A_%s"%d] for d in self.delta_virs])
            a_array = np.array([self.params["a_%s"%d] for d in self.delta_virs])
            b_array = np.array([self.params["b_%s"%d] for d in self.delta_virs])
            c_array = np.array([self.params["c_%s"%d] for d in self.delta_virs])

            A_func = _spline(self.delta_virs, A_array)
            a_func = _spline(self.delta_virs, a_array)
            b_func = _spline(self.delta_virs, b_array)
            c_func = _spline(self.delta_virs, c_array)

            A_0 = A_func(self.delta_halo)
            a_0 = a_func(self.delta_halo)
            b_0 = b_func(self.delta_halo)
            c_0 = c_func(self.delta_halo)
        else:
            A_0 = self.params["A_%s"%(int(self.delta_halo))]
            a_0 = self.params["a_%s"%(int(self.delta_halo))]
            b_0 = self.params["b_%s"%(int(self.delta_halo))]
            c_0 = self.params["c_%s"%(int(self.delta_halo))]

        self.A = A_0*(1 + self.z)**(-self.params["A_exp"])
        self.a = a_0*(1 + self.z)**(-self.params["a_exp"])
        alpha = 10**(-(0.75/np.log10(self.delta_halo/75))**1.2)
        self.b = b_0*(1 + self.z)**(-alpha)
        self.c = c_0

    @property
    def fsigma(self):
        return self.A*((self.sigma/self.b)**(-self.a) + 1)*np.exp(-self.c/self.sigma**2)

    @property
    def cutmask(self):
        if self.z == 0.0:
            return np.logical_and(self.lnsigma/np.log(10) > -0.6,
                                  self.lnsigma/np.log(10) < 0.4)
        else:
            return np.logical_and(self.lnsigma/np.log(10) > -0.2,
                                  self.lnsigma/np.log(10) < 0.4)


class Tinker10(FittingFunction):
    req_z = True
    req_dhalo = True

    _eq = r"(1+(\beta\nu)^{-2\phi})\nu^{2\eta+1}\exp(-\gamma\nu^2/2)"
    _ref = """Tinker, J., et al., 2010. ApJ 724, 878. http://iopscience.iop.org/0004-637X/724/2/878/pdf/apj_724_2_878.pdf"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Tinker10", "Tkr", _eq, _ref)

    sim_definition = copy(Tinker08.sim_definition)

    _defaults = {  # --- alpha
        "alpha_200": 0.368, "alpha_300": 0.363, "alpha_400": 0.385,
        "alpha_600": 0.389, "alpha_800": 0.393, "alpha_1200": 0.365,
        "alpha_1600": 0.379, "alpha_2400": 0.355, "alpha_3200": 0.327,
        # --- beta
        "beta_200": 0.589, "beta_300": 0.585, "beta_400": 0.544, "beta_600": 0.543,
        "beta_800": 0.564, "beta_1200": 0.623, "beta_1600": 0.637, "beta_2400": 0.673,
        "beta_3200": 0.702,
        # --- gamma
        "gamma_200": 0.864, "gamma_300": 0.922, "gamma_400": 0.987,
        "gamma_600": 1.09, "gamma_800": 1.2, "gamma_1200": 1.34,
        "gamma_1600": 1.5, "gamma_2400": 1.68, "gamma_3200": 1.81,
        # --- phi
        "phi_200": -0.729, "phi_300": -0.789, "phi_400": -0.910,
        "phi_600": -1.05, "phi_800": -1.2, "phi_1200": -1.26,
        "phi_1600": -1.45, "phi_2400": -1.5, "phi_3200": -1.49,
        # -- eta
        "eta_200": -0.243, "eta_300": -0.261, "eta_400": -0.261,
        "eta_600": -0.273, "eta_800": -0.278, "eta_1200": -0.301,
        "eta_1600": -0.301, "eta_2400": -0.319, "eta_3200": -0.336,
        # --others
        "beta_exp": 0.2, "phi_exp": -0.08, "eta_exp": 0.27, "gamma_exp": -0.01,
        "max_z": 3
    }

    delta_virs = np.array([200, 300, 400, 600, 800, 1200, 1600, 2400, 3200])
    terminate = True

    def __init__(self, **model_parameters):
        super(Tinker10, self).__init__(**model_parameters)

        if self.delta_halo not in self.delta_virs:
            beta_array = np.array([self.params["beta_%s"%d] for d in self.delta_virs])
            gamma_array = np.array([self.params["gamma_%s"%d] for d in self.delta_virs])
            phi_array = np.array([self.params["phi_%s"%d] for d in self.delta_virs])
            eta_array = np.array([self.params["eta_%s"%d] for d in self.delta_virs])

            beta_func = _spline(self.delta_virs, beta_array)
            gamma_func = _spline(self.delta_virs, gamma_array)
            phi_func = _spline(self.delta_virs, phi_array)
            eta_func = _spline(self.delta_virs, eta_array)

            beta_0 = beta_func(self.delta_halo)
            gamma_0 = gamma_func(self.delta_halo)
            phi_0 = phi_func(self.delta_halo)
            eta_0 = eta_func(self.delta_halo)
        else:
            beta_0 = self.params['beta_%s'%(int(self.delta_halo))]
            gamma_0 = self.params['gamma_%s'%(int(self.delta_halo))]
            phi_0 = self.params['phi_%s'%(int(self.delta_halo))]
            eta_0 = self.params['eta_%s'%(int(self.delta_halo))]

        self.beta = beta_0*(1 + min(self.z, self.params["max_z"]))**self.params["beta_exp"]
        self.phi = phi_0*(1 + min(self.z, self.params["max_z"]))**self.params['phi_exp']
        self.eta = eta_0*(1 + min(self.z, self.params["max_z"]))**self.params['eta_exp']
        self.gamma = gamma_0*(1 + min(self.z, self.params["max_z"]))**self.params['gamma_exp']

        # # The normalisation only works with specific conditions
        # gamma > 0
        if self.gamma <= 0:
            if self.terminate:
                raise ValueError("gamma must be > 0, got " + str(self.gamma))
            else:
                self.gamma = 1e-3
        # eta >-0.5
        if self.eta <= -0.5:
            if self.terminate:
                raise ValueError("eta must be > -0.5, got " + str(self.eta))
            else:
                self.eta = -0.499
        # eta-phi >-0.5
        if self.eta - self.phi <= -0.5:
            if self.terminate:
                raise ValueError("eta-phi must be >-0.5, got " + str(self.eta - self.phi))
            else:
                self.phi = self.eta + 0.499
        if self.beta <= 0:
            if self.terminate:
                raise ValueError("beta must be > 0, got " + str(self.beta))
            else:
                self.beta = 1e-3

    @property
    def normalise(self):
        if self.delta_halo in self.delta_virs and self.z == 0:
            return self.params['alpha_%s'%(int(self.delta_halo))]
        else:
            return 1/(2**(self.eta - self.phi - 0.5)*self.beta**(-2*self.phi) \
                      *self.gamma**(-0.5 - self.eta)*(2**self.phi*self.beta**(2*self.phi) \
                                                      *sp.gamma(self.eta + 0.5) + self.gamma**self.phi*sp.gamma(
                0.5 + self.eta - self.phi)))

    @property
    def fsigma(self):
        fv = (1 + (self.beta*self.nu)**(-2*self.phi))* \
             self.nu**(2*self.eta)*np.exp(-self.gamma*(self.nu**2)/2)

        return fv*self.normalise*self.nu

    @property
    def cutmask(self):
        if self.z == 0.0:
            return np.logical_and(self.lnsigma/np.log(10) > -0.6,
                                  self.lnsigma/np.log(10) < 0.4)
        else:
            return np.logical_and(self.lnsigma/np.log(10) > -0.2,
                                  self.lnsigma/np.log(10) < 0.4)


class Behroozi(Tinker10):
    _ref = r"""Behroozi, P., Weschler, R. and Conroy, C., ApJ, 2013, http://arxiv.org/abs/1207.6105"""
    __doc__ = """
    Behroozi mass function fit [1]_.

    This is an empirical modification to the :class:`Tinker08` fit, to improve
    accuracy at high redshift.

    %s

    References
    ----------
    .. [1] %s
    """%(FittingFunction._pdocs, _ref)

    sim_definition = SimDetails(L=[250,1000,420],
                                N=[2048**3,2048**3,1400**3],
                                halo_finder_type="SO",
                                omegam=0.27,
                                sigma_8=0.82,
                                halo_overdensity=178,
                                halo_finder="Rockstar",
                                softening=[1,7,8],
                                transfer="CAMB",
                                z_start=None,
                                z_meas=(0,8),
                                ICS=["1LPT","1LPT","2LPT"],
                                nmin=None,
                                hmf_analysis_notes="No corrections applied.",
                                other_cosmo={"omegav": 0.73,
                                             "omegab":None, ## uses lower case omega without definition
                                             "h":0.7,
                                             "n": 0.95})

    def _modify_dndm(self, m, dndm, z, ngtm_tinker):
        a = 1/(1 + z)
        theta = 0.144/(1 + np.exp(14.79*(a - 0.213)))*(m/10**11.5)**(0.5/(1 + np.exp(6.5*a)))
        ngtm_behroozi = 10**(theta + np.log10(ngtm_tinker))
        dthetadM = 0.144/(1 + np.exp(14.79*(a - 0.213)))* \
                   (0.5/(1 + np.exp(6.5*a)))*(m/10**11.5)** \
                                             (0.5/(1 + np.exp(6.5*a)) - 1)/(10**11.5)
        # if ngtm_tinker is very small (ie. 0), dthetadM will be nan.
        res = dndm*10**theta - ngtm_behroozi*np.log(10)*dthetadM
        res[np.isnan(res)] = 0
        return res


class Pillepich(Warren):
    _ref = r"""Pillepich, A., et al., 2010, arxiv:0811.4176"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Pillepich", "Pillepich", Warren._eq, _ref)
    _defaults = {"A": 0.6853, "b": 1.868, "c": 0.3324, "d": 1.2266, "e": 1}

    sim_definition = SimDetails(L=[1200,1200,150],
                                N=[1024**3,1024**3,1024**3],
                                halo_finder_type="FoF",
                                omegam=[0.279,0.24,0.279],
                                sigma_8=[0.817,0.76,0.817],
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[20,20,3],
                                transfer="LINGER",
                                z_start=[50,50,70],
                                z_meas=0,
                                ICS="1LPT",
                                nmin=100,
                                hmf_analysis_notes="No corrections applied.",
                                other_cosmo={"omegav": [0.721,0.76,0.721],
                                             "omegab":[0.0462,0.042,0.0462], ## uses lower case omega without definition
                                             "h":[0.701,0.73,0.701],
                                             "n": [0.96,0.95,0.96]})


class Manera(SMT):
    _ref = r"""Manera, M., et al., 2010, arxiv:0906.1314"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Manera", "Man", SMT._eq, _ref)
    # These are for z=0, new ML method, l_linnk = 0.2
    _defaults = {"A": None, "a": 0.709, "p": 0.289}

    sim_definition = SimDetails(L=1280.0,
                                N=640**3,
                                halo_finder_type="FoF",
                                omegam=0.27,
                                sigma_8=0.9,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=20,
                                transfer="CMBFAST",
                                z_start=50,
                                z_meas=(0,0.5),
                                ICS="2LPT",
                                nmin=105,
                                hmf_analysis_notes="FOF Correction applied.",
                                other_cosmo={"omegav": 0.73,
                                             "omegab":0.046, ## uses lower case omega without definition
                                             "h":0.72,
                                             "n": 1.0})


class Ishiyama(Warren):
    _eq = r"A\left[\left(\frac{e}{\sigma}\right)^b + 1\right]\exp(\frac{d}{\sigma^2})"
    _ref = r"""Ishiyama, T., et al., 2015, arxiv:1412.2860"""
    __doc__ = _makedoc(FittingFunction._pdocs, "Ishiyama", "Ishiyama", _eq, _ref)

    _defaults = {"A": 0.193, "b": 1.550, "c": 1, "d": 1.186, "e": 2.184}

    sim_definition = SimDetails(L=[1120,560,280,140,70],
                                N=[8192**3,4096**3,2048**3,2048**3,2048**3],
                                halo_finder_type="FoF",
                                omegam=0.31,
                                sigma_8=0.83,
                                halo_overdensity=0.2,
                                halo_finder=None,
                                softening=[4.27,4.27,4.27,2.14,1.07],
                                transfer="CAMB",
                                z_start=None,
                                z_meas=0,
                                ICS=None,
                                nmin=40,
                                hmf_analysis_notes="No corrections applied.",
                                other_cosmo={"omegav": 0.69,
                                             "omegab":0.048, ## uses lower case omega without definition
                                             "h":0.68,
                                             "n": 0.96})
    @property
    def cutmask(self):
        return np.logical_and(self.m > 1e8, self.m < 1e16)

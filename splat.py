# WORKING COPY OF SPLAT CODE LIBRARY
# based on routines developed by:
#    Christian Aganze
#    Daniella Bardalez Gagliuffi
#    Adam Burgasser
#    Caleb Choban
#    Ivanna Escala
#    Aishwarya Iyer
#    Yuhui Jin
#    Michael Lopez
#    Alex Mendez
#    Jonathan Parra
#    Julian Pilate-Hutcherson
#    Maitrayee Sahi
#    Melisa Tallis

#
# CURRENT STATUS (9/2/2014)
# Several models are now available, although this is somewhat unstable
# due to patchy parameter coverage
# Units are integrated, although somewhat haphazardly
# Need to spruce up plotSpectrum (more options)
# Need to add more filters
# Need to add better metadata for Spectrum object (headers)

# imports
import astropy
import base64
import copy
import glob
import matplotlib.pyplot as plt
import numpy
import os
import random
import re
import scipy
import string
import sys
import urllib2
import warnings

from scipy import stats, signal
from scipy.integrate import trapz        # for numerical integration
from scipy.interpolate import interp1d, griddata
from astropy.io import ascii, fits            # for reading in spreadsheet
from astropy.table import Table, join            # for reading in table files
from astropy.coordinates import SkyCoord      # coordinate conversion
from astropy import units as u            # standard units
from astropy import constants as const        # physical constants in SI units

# local application/library specific import
from bdevopar import *

# suppress warnings - probably not an entirely safe approach!
numpy.seterr(all='ignore')
warnings.simplefilter("ignore")
#from splat._version import __version__

#set the SPLAT PATH, either from set environment variable or from sys.path
SPLAT_PATH = './'
if os.environ.get('SPLAT_PATH') != None:
    SPLAT_PATH = os.environ['SPLAT_PATH']
else:
    checkpath = ['splat' in r for r in sys.path]
    if max(checkpath):
        SPLAT_PATH = sys.path[checkpath.index(max(checkpath))]

#################### CONSTANTS ####################
SPLAT_URL = 'http://pono.ucsd.edu/~adam/splat/'
SPECTRAL_MODEL_FOLDER = '/SpectralModels/'
EVOLUTIONARY_MODEL_FOLDER = '/EvolutionaryModels/'
FILTER_FOLDER = '/Filters/'
DATA_FOLDER = '/Spectra/'

months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
spex_pixel_scale = 0.15            # spatial scale in arcseconds per pixel
spex_wave_range = [0.65,2.45]*u.micron    # default wavelength range
max_snr = 1000.0                # maximum S/N ratio permitted
MODEL_PARAMETER_NAMES = ['teff','logg','z','fsed','cld','kzz','slit']
MODEL_PARAMETERS = {'teff': 1000.0,'logg': 5.0,'z': 0.0,'fsed':'nc','cld':'nc','kzz':'eq','slit':0.5}
DEFINED_MODEL_SET = ['BTSettl2008','burrows06','morley12','morley14','saumon12','drift']
TMPFILENAME = 'splattmpfile'

spex_stdfiles = { \
    'M0.0': 'spex_prism_Gl270_091203.fits',\
    'M1.0': 'spex_prism_Gl424_091229.fits',\
    'M2.0': 'spex_prism_Gl91_081012.fits',\
    'M3.0': 'spex_prism_Gl752A_070704.fits',\
    'M4.0': 'spex_prism_Gl213_071110dl.fits',\
    'M5.0': 'spex_prism_Gl51_070728.fits',\
    'M6.0': 'spex_prism_LHS1375_081012.fits',\
    'M7.0': 'spex_prism_vB8_070704.fits',\
    'M8.0': 'spex_prism_vB10_070704.fits',\
    'M9.0': 'spex_prism_LHS2924_070704.fits',\
    'L0.0': 'spex_prism_0345+2540_kc.fits',\
    'L1.0': 'spex_prism_2130-0845_080713.fits',\
    'L2.0': 'spex_prism_kelu-1_060411.fits',\
    'L3.0': 'spex_prism_1506+1321_060410.fits',\
    'L4.0': 'spex_prism_2158-1550_060901.fits',\
    'L5.0': 'spex_prism_sdss0835+19_chiu06.fits',\
    'L6.0': 'spex_prism_1010-0406_kc.fits',\
    'L7.0': 'spex_prism_0103+1935_060902.fits',\
    'L8.0': 'spex_prism_1632+1904_030905.fits',\
    'L9.0': 'spex_prism_denis0255-4700_040908.fits',\
    'T0.0': 'spex_prism_1207+0244_061221dl.fits',\
    'T1.0': 'spex_prism_0837-0000_061221.fits',\
    'T2.0': 'spex_prism_sdss1254-0122_030522.fits',\
    'T3.0': 'spex_prism_1209-1004_030523.fits',\
    'T4.0': 'spex_prism_2254+3123_030918.fits',\
    'T5.0': 'spex_prism_1503+2525_030522.fits',\
    'T6.0': 'spex_prism_sdss1624+0029_040312.fits',\
    'T7.0': 'spex_prism_0727+1710_040310.fits',\
    'T8.0': 'spex_prism_0415-0935_030917.fits',\
    'T9.0': 'spex_prism_0722-0540_110404.fits'}

#####################################################

        
# helper functions from Alex
def lazyprop(fn):
     attr_name = '_lazy_' + fn.__name__
     @property
     def _lazyprop(self):
          if not hasattr(self, attr_name):
                setattr(self, attr_name, fn(self))
          return getattr(self, attr_name)
     return _lazyprop

def Show(fn):
     def _show(self, *args, **kwargs):
          noplot = kwargs.pop('noplot', False)
          quiet = kwargs.pop('quiet', False)
          tmp = fn(self, *args, **kwargs)
#         if not quiet:
#                self.info()
#          if not noplot:
#                self.plot(**kwargs)
          return tmp
     return _show

def Copy(fn):
     def _copy(self, *args, **kwargs):
          out = copy.copy(self)
          return fn(out, *args, **kwargs)
     return _copy


# define the Spectrum class which contains the relevant information
class Spectrum(object):
    @Show
    def __init__(self, **kwargs):
        '''Load the file'''
        self.model = False
# various options for setting the filename
        self.filename = ''
        if kwargs.get('filename','') != '':
            self.filename = kwargs.get('filename','')
        if kwargs.get('file','') != '':
            self.filename = kwargs.get('file','')
        kwargs['filename'] = self.filename
        self.wlabel = kwargs.get('wlabel',r'Wavelength')
        self.wunit = kwargs.get('wunit',u.micron)
        self.flabel = kwargs.get('flabel',r'F$_{\lambda}$')
        self.fscale = kwargs.get('fscale','')
        self.funit = kwargs.get('funit',u.erg/(u.cm**2 * u.s * u.micron))
        self.resolution = kwargs.get('resolution',150)    # default placeholder
        self.slitpixelwidth = kwargs.get('slitwidth',3.33)        # default placeholder
        self.slitwidth = self.slitpixelwidth*spex_pixel_scale
        self.simplefilename = os.path.basename(self.filename)
        self.header = kwargs.get('header',Table())
# wave and flux given
        if len(kwargs.get('wave','')) > 0 and len(kwargs.get('flux','')) > 0:
            self.wave = kwargs['wave']
            self.flux = kwargs['flux']
            if len(kwargs.get('noise','')) > 0:
                self.noise = kwargs['noise']
            else:
                self.noise = numpy.array([numpy.nan for i in self.wave])
        else:
# filename given
#            print kwargs['filename']
            rs = readSpectrum(**kwargs)
            try:
                self.wave = rs['wave']
                self.flux = rs['flux']
                self.noise = rs['noise']
                self.header = rs['header']
            except:
                raise NameError('\nCould not load up spectral file {:s}'.format(kwargs.get('filename','')))
# convert to numpy arrays
        self.wave = numpy.array(self.wave)
        self.flux = numpy.array(self.flux)
        self.noise = numpy.array(self.noise)
# enforce positivity and non-nan
        if (numpy.nanmin(self.flux) < 0):
            self.flux[numpy.where(self.flux < 0)] = 0.
        self.flux[numpy.isnan(self.flux)] = 0.
# check on noise being too low
        if (numpy.nanmax(self.flux/self.noise) > max_snr):
            self.noise[numpy.where(self.flux/self.noise > max_snr)]=numpy.median(self.noise)
# convert to astropy quantities with units
# assuming input is flam in erg/s/cm2/micron
        if ~isinstance(self.wave,astropy.units.quantity.Quantity):
            self.wave = numpy.array(self.wave)*self.wunit
        if ~isinstance(self.flux,astropy.units.quantity.Quantity):
            self.flux = numpy.array(self.flux)*self.funit
        if ~isinstance(self.wave,astropy.units.quantity.Quantity):
            self.noise = numpy.array(self.noise)*self.funit
# some conversions
        self.flam = self.flux
        self.nu = self.wave.to('Hz',equivalencies=u.spectral())
        self.fnu = self.flux.to('Jy',equivalencies=u.spectral_density(self.wave))
        self.fnunit = u.Jansky
# calculate variance
        self.variance = self.noise**2
        self.dof = numpy.round(len(self.wave)/self.slitpixelwidth)
# signal to noise
        w = numpy.where(self.flux.value > numpy.median(self.flux.value))
        self.snr = numpy.nanmean(self.flux.value[w]/self.noise.value[w])

# preserve original values
        self.wave_original = copy.deepcopy(self.wave)
        self.flux_original = copy.deepcopy(self.flux)
        self.noise_original = copy.deepcopy(self.noise)
        self.variance_original = copy.deepcopy(self.variance)
        self.resolution = copy.deepcopy(self.resolution)
        self.slitpixelwidth = copy.deepcopy(self.slitpixelwidth)
        
# information on source spectrum
        if not (kwargs.get('model',False)):
            x,y = filenameToNameDate(self.filename)
            self.name = kwargs.get('name',x)
            self.date = kwargs.get('date',y)
            try:
                self.caldate = dateToCaldate(self.date)
            except:
                self.caldate = ''
        else:
# information on model
            self.model = True
            self.teff = kwargs.get('teff',numpy.nan)
            self.logg = kwargs.get('logg',numpy.nan)
            self.z = kwargs.get('z',numpy.nan)
            self.fsed = kwargs.get('fsed',numpy.nan)
            self.cld = kwargs.get('cld',numpy.nan)
            self.kzz = kwargs.get('kzz',numpy.nan)
            self.slit = kwargs.get('slit',numpy.nan)
            self.modelset = kwargs.get('set','')
            self.name = self.modelset+' Teff='+str(self.teff)+' logg='+str(self.logg)
            self.fscale = 'Surface'
        self.history = ['Loaded']

                
    def __repr__(self):
        '''A simple representation of an object is to just give it a name'''
        return 'Spectra Object for {}'.format(self.name)

    def __add__(self,other):
        '''Adding two spectra '''
        sp = copy.deepcopy(self)
        f = interp1d(other.wave,other.flux,bounds_error=False,fill_value=0.)
        n = interp1d(other.wave,other.variance,bounds_error=False,fill_value=numpy.nan)
        sp.flux = numpy.add(self.flux,f(self.wave)*other.funit)
        sp.variance = sp.variance+n(self.wave)*(other.funit**2)
        sp.noise = sp.variance**0.5
        sp.flux_original=sp.flux
        sp.noise_original=sp.noise
        sp.variance_original=sp.variance
        return sp

    def __sub__(self,other):
        '''Subtracting two spectra '''
        sp = copy.deepcopy(self)
        f = interp1d(other.wave,other.flux,bounds_error=False,fill_value=0.)
        n = interp1d(other.wave,other.variance,bounds_error=False,fill_value=numpy.nan)
        sp.flux = numpy.subtract(self.flux,f(self.wave)*other.funit)
        sp.variance = sp.variance+n(self.wave)*(other.funit**2)
        sp.noise = sp.variance**0.5
        sp.flux_original=sp.flux
        sp.noise_original=sp.noise
        sp.variance_original=sp.variance
        return sp

    def __mul__(self,other):
        '''Multiplying two spectra'''
        sp = copy.deepcopy(self)
        f = interp1d(other.wave,other.flux,bounds_error=False,fill_value=0.)
        n = interp1d(other.wave,other.variance,bounds_error=False,fill_value=numpy.nan)
        sp.flux = numpy.multiply(self.flux,f(self.wave)*other.funit)
        sp.variance = numpy.multiply(numpy.power(sp.flux,2),(\
            numpy.divide(self.variance,numpy.power(sp.flux,2))+\
            numpy.divide(n(self.wave)*(other.funit**2),numpy.power(f(self.wave),2))))
        sp.noise = sp.variance**0.5
        sp.flux_original=sp.flux
        sp.noise_original=sp.noise
        sp.variance_original=sp.variance
        return sp

    def __div__(self,other):
        '''Dividing two spectra'''
        sp = copy.deepcopy(self)
        f = interp1d(other.wave,other.flux,bounds_error=False,fill_value=0.)
        n = interp1d(other.wave,other.variance,bounds_error=False,fill_value=numpy.nan)
        sp.flux = numpy.divide(self.flux,f(self.wave)*other.funit)
        sp.variance = numpy.multiply(numpy.power(sp.flux,2),(\
            numpy.divide(self.variance,numpy.power(sp.flux,2))+\
            numpy.divide(n(self.wave)*(other.funit**2),numpy.power(f(self.wave),2))))
        sp.noise = sp.variance**0.5
        sp.flux_original=sp.flux
        sp.noise_original=sp.noise
        sp.variance_original=sp.variance
        return sp

# NOTE: COPY CURRENTLY NOT FUNCTIONAL
    def copy(self):
        '''Make a copy of the current spectrum'''
        other = copy.deepcopy(self)
        return other
#          return type('CopyOfB', B.__bases__, dict(B.__dict__))

    def info(self):
          '''Report some information about this spectrum'''
          if (self.model):
              print '\n{} model with the following parmeters:'.format(self.modelset)
              print 'Teff = {}'.format(self.teff)
              print 'logg = {}'.format(self.logg)
              print 'z = {}'.format(self.z)
              print 'fsed = {}'.format(self.fsed)
              print 'cld = {}'.format(self.cld)
              print 'kzz = {}'.format(self.kzz)
              print 'slit = {}\n'.format(self.slit)
          else:
              print '''Spectrum of {0} taken on {1}'''.format(self.name, self.date)
          return

    def flamToFnu(self):
         '''Convert flux density from F_lam to F_nu, the later in Jy'''
         self.funit = u.Jy
         self.flabel = 'F_nu'
         self.flux.to(self.funit,equivalencies=u.spectral_density(self.wave))
         self.noise.to(self.funit,equivalencies=u.spectral_density(self.wave))
         return

    def fluxCalibrate(self,filter,mag,**kwargs):
        '''Calibrate spectrum to input magnitude'''
        absolute = kwargs.get('absolute',False)
        apparent = kwargs.get('apparent',False)
        self.normalize()
        apmag,apmag_e = filterMag(self,filter,**kwargs)
# NOTE: NEED TO INCORPORATE UNCERTAINTY INTO SPECTRAL UNCERTAINTY
        if (~numpy.isnan(apmag)):
            self.scale(10.**(0.4*(apmag-mag)))
            if (absolute):
                self.fscale = 'Absolute'
            if (apparent):
                self.fscale = 'Apparent'
        return

    def fluxMax(self):
        return numpy.nanmax(self.flux.value[numpy.where(\
            numpy.logical_and(self.wave > 0.8*u.micron,self.wave < 2.3*u.micron))])*self.funit

    def fnuToFlam(self):
         '''Convert flux density from F_nu to F_lam, the later in erg/s/cm2/Hz'''
         self.funit = u.erg/(u.cm**2 * u.s * u.micron)
         self.flabel = 'F_lam'
         self.flux.to(self.funit,equivalencies=u.spectral_density(self.wave))
         self.noise.to(self.funit,equivalencies=u.spectral_density(self.wave))
         self.variance = self.noise**2
         return

    def normalize(self):
        '''Normalize spectrum'''
        self.scale(1./self.fluxMax())
        self.fscale = 'Normalized'
        return

    def reset(self):
        '''Reset to original spectrum'''
        self.wave = copy.deepcopy(self.wave_original)
        self.flux = copy.deepcopy(self.flux_original)
        self.noise = copy.deepcopy(self.noise_original)
        self.variance = copy.deepcopy(self.variance_original)
        self.resolution = copy.deepcopy(self.resolution_original)
        self.slitpixelwidth = copy.deepcopy(self.slitpixelwidth_original)
        self.slitwidth = self.slitpixelwidth*spex_pixel_scale
        self.fscale = ''
        return

    def scale(self,factor):
         '''Scale spectrum and noise by a constant factor'''
         self.flux = self.flux*factor
         self.noise = self.noise*factor
         self.variance = self.noise**2
         self.fscale = 'Scaled'
         return
        
    def smooth(self,**kwargs):
        '''Smooth spectrum to a constant slit width (smooth by pixels)'''
        method = kwargs.get('method','hanning')
        kwargs['method'] = method
        swargs = copy.deepcopy(kwargs)
        if (kwargs.get('slitPixelWidth','') != ''):
            del swargs['slitPixelWidth']
            self.smoothToSlitPixelWidth(kwargs['slitPixelWidth'],**swargs)
        elif (kwargs.get('resolution','') != ''):
            del swargs['resolution']
            self.smoothToResolution(kwargs['resolution'],**swargs)
        elif (kwargs.get('slitWidth','') != ''):
            del swargs['slitWidth']
            self.smoothToSlitWidth(kwargs['slitWidth'],**swargs)
        return

    def smoothToResolution(self,resolution,**kwargs):
        '''Smooth spectrum to a constant resolution'''
        overscale = kwargs.get('overscale',10.)
        method = kwargs.get('method','hanning')
        kwargs['method'] = method

# do nothing if requested resolution is higher than current resolution
        if (resolution < self.resolution):
# sample onto a constant resolution grid at 5x current resolution
             r = resolution*overscale
             waveRng = self.waveRange()
             npix = numpy.floor(numpy.log(waveRng[1]/waveRng[0])/numpy.log(1.+1./r))
             wave_sample = [waveRng[0]*(1.+1./r)**i for i in numpy.arange(npix)]
             f = interp1d(self.wave,self.flux,bounds_error=False,fill_value=0.)
             v = interp1d(self.wave,self.variance,bounds_error=False,fill_value=numpy.nan)
             flx_sample = f(wave_sample)*self.funit
             var_sample = v(wave_sample)*self.funit**2
# now convolve a function to smooth resampled spectrum
             window = signal.get_window(method,numpy.round(overscale))
             neff = numpy.sum(window)/numpy.nanmax(window)        # effective number of pixels
             flx_smooth = signal.convolve(flx_sample, window/numpy.sum(window), mode='same')
             var_smooth = signal.convolve(var_sample, window/numpy.sum(window), mode='same')/neff
# resample back to original wavelength grid
             f = interp1d(wave_sample,flx_smooth,bounds_error=False,fill_value=0.)
             v = interp1d(wave_sample,var_smooth,bounds_error=False,fill_value=0.)
             self.flux = f(self.wave)*self.funit
             self.variance = v(self.wave)*self.funit**2
             self.noise = numpy.array([n**0.5 for n in self.variance])
             self.slitpixelwidth = self.slitpixelwidth*self.resolution/resolution
             self.resolution = resolution
             self.slitwidth = self.slitpixelwidth*spex_pixel_scale
             self.history = ['Smoothed to constant resolution {}'.format(self.resolution)]        
        return

    def smoothToSlitPixelWidth(self,width,**kwargs):
        '''Smooth spectrum to a constant slit width (smooth by pixels)'''
        method = kwargs.get('method','hanning')
        kwargs['method'] = method
# do nothing if requested resolution is higher than current resolution
        if (width > self.slitpixelwidth):
# convolve a function to smooth spectrum
            window = signal.get_window(method,numpy.round(width))
            neff = numpy.sum(window)/numpy.nanmax(window)        # effective number of pixels
            self.flux = signal.convolve(self.flux, window/numpy.sum(window), mode='same')
            self.variance = signal.convolve(self.variance, window/numpy.sum(window), mode='same')/neff
            self.noise = numpy.array([n**0.5 for n in self.variance])
            self.resolution = self.resolution*self.slitpixelwidth/width
            self.slitpixelwidth = width
            self.slitwidth = self.slitpixelwidth*spex_pixel_scale
            self.history = ['Smoothed to slit width of {}'.format(self.slitwidth)]        
        return

    def smoothToSlitWidth(self,width,**kwargs):
        method = kwargs.get('method','hanning')
        kwargs['method'] = method
        '''Smooth spectrum to a constant slit width (smooth by pixels)'''
        pwidth = width/spex_pixel_scale
        self.smoothToSlitPixelWidth(pwidth,**kwargs)
        return

    def snr(self):
        '''Compute a representative S/N value'''
        pass
        return

    def surface(self,radius):
         '''Convert to surface fluxes given a radius, assuming at absolute fluxes'''
         pass
         return

    def waveRange(self):
        ii = numpy.where(self.flux.value > 0)
        return [numpy.nanmin(self.wave[ii]), numpy.nanmax(self.wave[ii])]
     
        
                             

# FUNCTIONS FOR SPLAT
def caldateToDate(d):
    '''
    :Purpose: ``Convert from numeric date to calendar date, and vice-versa.``
    :param d: ``A numeric date of the format '20050412', or a date in the 
                calendar format '2005 Jun 12'``
    :Example:
       >>> import splat
       >>> caldate = splat.dateToCaldate('20050612')
       >>> print caldate
       2005 Jun 12
       >>> date = splat.caldateToDate('2005 June 12')
       >>> print date
       20050612
    '''
    return d[:4]+str((months.index(d[5:8])+1)/100.)[2:4]+d[-2:]


def checkFile(filename,**kwargs):
    '''
    :Purpose: ``Checks if a spectrum file exists in the SPLAT's library.``
    :param filename: ``A string containing the spectrum's filename.``
    :Example: 
       >>> import splat
       >>> spectrum1 = 'spex_prism_1315+2334_110404.fits'
       >>> print splat.checkFile(spectrum1)
       True
       >>> spectrum2 = 'fake_name.fits'
       >>> print splat.checkFile(spectrum2)
       False
    '''
    url = kwargs.get('url',SPLAT_URL)+'/Spectra/'
    flag = checkOnline()
    if (flag):
        try:
            open(os.path.basename(filename), 'wb').write(urllib2.urlopen(url+filename).read())
        except urllib2.URLError:
            flag = False
    return flag


def checkAccess(**kwargs):
    '''
    :Purpose: ``Checks if user has access to unpublished spectra in SPLAT library.``
    :Example: 
       >>> import splat
       >>> print splat.checkAccess()
       True
    :Note: ``Must have the file .splat_access in your home directory with the correct passcode to use.``
    '''
    access_file = '.splat_access'
    result = False

    try:
        home = os.environ.get('HOME')
        if home == None:
            home = './'
        bcode = urllib2.urlopen(SPLAT_URL+access_file).read()
        lcode = base64.b64encode(open(home+'/'+access_file,'r').read())
        if (bcode in lcode):        # changed to partial because of EOL variations
            result = True
    except:
        result = False

    if (kwargs.get('report','') != ''):
        if result == True:
            print 'You have full access to all SPLAT data'
        else:
            print 'You have access only to published data'
    return result
    

def checkLocal(file):
    '''
    :Purpose: ``Checks if a file is present locally or within the SPLAT
                code directory'' 
    :Example:
       >>> import splat
       >>> splat.checkLocal('splat.py')
       True  # found the code
       >>> splat.checkLocal('parameters.txt')
       False  # can't find this file
       >>> splat.checkLocal('SpectralModels/BTSettl08/parameters.txt')
       True  # found it
    '''
    if not os.path.exists(file):
        if not os.path.exists(SPLAT_PATH+file):
            return False
        else:
            return True
    else:
        return True


def checkOnline(*args):
    '''
    :Purpose: ``Checks if SPLAT's URL is accessible from your machine--
                that is, checks if you and the host are online. Alternately
                checks if a given filename is present locally or online''
    :Example:
       >>> import splat
       >>> splat.checkOnline()
       True  # SPLAT's URL was detected.
       >>> splat.checkOnline()
       False # SPLAT's URL was not detected.
       >>> splat.checkOnline('SpectralModels/BTSettl08/parameters.txt')
       False # Could not find this online file.
    '''
    if (len(args) != 0):
        try:
            open(os.path.basename(TMPFILENAME), 'wb').write(urllib2.urlopen(SPLAT_URL+args[0]).read())
            os.remove(os.path.basename(TMPFILENAME))
            return True
#            return data
        except urllib2.URLError:
            return False

    else:
        try:
            urllib2.urlopen(SPLAT_URL)
            return True
        except urllib2.URLError:
            return False



def classifyByIndex(sp, *args, **kwargs):
    '''
    :Purpose: ``Determine the spectral type and uncertainty for a spectrum 
                based on indices. Makes use of published index-SpT relations
                from Reid et al. (2001); Testi et al. (2001); Allers et al. 
                (2007); and Burgasser (2007). Returns 2-element tuple 
                containing spectral type (numeric or string) and 
                uncertainty.``
    :param sp: ``Spectrum class object, which should contain wave, flux and 
                 noise array elements.``
    :param \**kwargs (optional): - ``set = 'burgasser': named set of indices to measure and compute spectral type:``
                          * ``'allers': H2O from Allers et al.``
                          * ``'burgasser': H2O-J, CH4-J, H2O-H, CH4-H, 
                            CH4-K from Burgasser (2007)``
                          * ``'reid':H2O-A and H2O-B from Reid et al.(2001)``
                          * ``'testi': sHJ, sKJ, sH2O_J, sH2O_H1, sH2O_H2, 
                            sH2O_K from Testi et al. (2001)``
                      - ``string = False: return spectral type as a string 
                        (uses typeToNum)``
                      - ``round = False: rounds off to nearest 0.5 subtypes``
                      - ``remeasure = True: force remeasurement of indices``
                      - ``nsamples = 100: number of Monte Carlo samples for 
                        error computation``
                      - ``nloop = 5: number of testing loops to see if 
                        spectral type is within a certain range``

    :Example:
       >>> import splat
       >>> spc = splat.loadSpectrum('spex_prism_gl570d_030522.txt')
       >>> print splat.classifyByIndex(spc, string=True, set='burgasser', round=True)
       ('T7.5', 0.25285169510990341)
    :Things to Update
        * Need to allow output of individual spectral types from individual indices
    '''
    
    str_flag = kwargs.get('string', True)
    rnd_flag = kwargs.get('round', False)
    rem_flag = kwargs.get('remeasure', True)
    nsamples = kwargs.get('nsamples', 100)
    nloop = kwargs.get('nloop', 5)
    set = kwargs.get('set','burgasser')
    set = kwargs.get('ref',set)
    kwargs['set'] = set
    allowed_sets = ['burgasser','reid','testi','allers']
    if (set.lower() not in allowed_sets):
        print '\nWarning: index classification method {} not present; returning nan\n\n'.format(set)
        return numpy.nan, numpy.nan

# measure indices if necessary
    if (len(args) != 0):
        indices = args[0]

# Reid et al. (2001, AJ, 121, 1710)
    elif (set.lower() == 'reid'):
        if (rem_flag or len(args) == 0):
            indices = measureIndexSet(sp, **kwargs)
        sptoffset = 20.
        sptfact = 1.
        coeffs = { \
            'H2O-A': {'fitunc': 1.18, 'range': [18,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [-32.1, 23.4]}, \
            'H2O-B': {'fitunc': 1.02, 'range': [18,28], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [-24.9, 20.7]}}

# Testi et al. (2001, ApJ, 522, L147)
    elif (set.lower() == 'testi'):
        if (rem_flag or len(args) == 0):
            indices = measureIndexSet(sp, **kwargs)
        sptoffset = 20.
        sptfact = 10.
        coeffs = { \
            'sHJ': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [-1.87, 1.67]}, \
            'sKJ': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [-1.20, 2.01]}, \
            'sH2O_J': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [1.54, 0.98]}, \
            'sH2O_H1': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [1.27, 0.76]}, \
            'sH2O_H2': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [2.11, 0.29]}, \
            'sH2O_K': {'fitunc': 0.5, 'range': [20,26], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [2.36, 0.60]}}

# Burgasser (2007, ApJ, 659, 655) calibration
    elif (set.lower() == 'burgasser'):
        if (rem_flag or len(args) == 0):
            indices = measureIndexSet(sp, **kwargs)
        sptoffset = 20.
        sptfact = 1.
        coeffs = { \
            'H2O-J': {'fitunc': 0.8, 'range': [20,39], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [1.038e2, -2.156e2,  1.312e2, -3.919e1, 1.949e1]}, \
            'H2O-H': {'fitunc': 1.0, 'range': [20,39], 'spt': 0., 'sptunc': 99., 'mask': 1.,  \
            'coeff': [9.087e-1, -3.221e1, 2.527e1, -1.978e1, 2.098e1]}, \
            'CH4-J': {'fitunc': 0.7, 'range': [30,39], 'spt': 0., 'sptunc': 99., 'mask': 1.,  \
            'coeff': [1.491e2, -3.381e2, 2.424e2, -8.450e1, 2.708e1]}, \
            'CH4-H': {'fitunc': 0.3, 'range': [31,39], 'spt': 0., 'sptunc': 99., 'mask': 1.,  \
            'coeff': [2.084e1, -5.068e1, 4.361e1, -2.291e1, 2.013e1]}, \
            'CH4-K': {'fitunc': 1.1, 'range': [20,37], 'spt': 0., 'sptunc': 99., 'mask': 1.,  \
            'coeff': [-1.259e1, -4.734e0, 2.534e1, -2.246e1, 1.885e1]}}

# Allers et al. (2013, ApJ, 657, 511)
    elif (set.lower() == 'allers'):
        if (rem_flag or len(args) == 0):
            kwargs['set'] = 'mclean'
            i1 = measureIndexSet(sp, **kwargs)
            kwargs['set'] = 'slesnick'
            i2 = measureIndexSet(sp, **kwargs)
            kwargs['set'] = 'allers'
            i3 = measureIndexSet(sp, **kwargs)
            indices = dict(i1.items() + i2.items() + i3.items())
        sptoffset = 10.
        sptfact = 1.
        coeffs = { \
            'H2O': {'fitunc': 0.390, 'range': [15,25], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [24.0476, -104.424, 169.388,-83.5437]}, \
            'H2O-1': {'fitunc': 1.097, 'range': [14,25], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [28.5982, -80.7404, 39.3513, 12.1927]}, \
            'H2OD': {'fitunc': 0.757, 'range': [20,28], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [-97.230, 229.884, -202.245, 79.4477]}, \
            'H2O-2': {'fitunc': 0.501, 'range': [14,22], 'spt': 0., 'sptunc': 99., 'mask': 1., \
            'coeff': [37.5013, -97.8144, 55.4580, 10.8822]}}

    else:
        sys.stderr.write('\nWarning: '+set.lower()+' SpT-index relation not in classifyByIndex code\n\n')
        return numpy.nan, numpy.nan


    for index in coeffs.keys():
        vals = numpy.polyval(coeffs[index]['coeff'],numpy.random.normal(indices[index][0],indices[index][1],nsamples))*sptfact
        coeffs[index]['spt'] = numpy.nanmean(vals)+sptoffset
        coeffs[index]['sptunc'] = (numpy.nanstd(vals)**2+coeffs[index]['fitunc']**2)**0.5
#        print index, indices[index], numpy.nanmean(vals), numpy.nanstd(vals), coeffs[index]['spt']
    
#    print indices[index][0], numpy.polyval(coeffs[index]['coeff'],indices[index][0]), coeffs[index]
#    mask = numpy.ones(len(coeffs.keys()))
#    result = numpy.zeros(2)
    for i in numpy.arange(nloop):
        wts = [coeffs[index]['mask']/coeffs[index]['sptunc']**2 for index in coeffs.keys()]
        if (numpy.nansum(wts) == 0.):
            sys.stderr.write('\nIndices do not fit within allowed ranges\n\n')
            return numpy.nan, numpy.nan            
        vals = [coeffs[index]['mask']*coeffs[index]['spt']/coeffs[index]['sptunc']**2 \
            for index in coeffs.keys()]
        sptn = numpy.nansum(vals)/numpy.nansum(wts)
        sptn_e = 1./numpy.nansum(wts)**0.5
        for index in coeffs.keys():
            coeffs[index]['mask'] = numpy.where( \
                coeffs[index]['range'][0] <= sptn <= coeffs[index]['range'][1],1,0)

# round off to nearest 0.5 subtypes if desired
    if (rnd_flag):
        sptn = 0.5*numpy.around(sptn*2.)

# change to string if desired
    if (str_flag):
        spt = typeToNum(sptn,uncertainty=sptn_e)
    else:
        spt = sptn

    return spt, sptn_e


def classifyByStandard(sp, *args, **kwargs):
    '''
    :Purpose: ``Determine the spectral type and uncertainty for a 
                spectrum by direct comparison to spectral standards. 
                Standards span M0-T9 and include the standards listed in 
                Kirkpatrick et al. (2010) with addition of UGPS 0722-0540 
                as the T9 standard.  Returns the best match or an F-test 
                weighted mean and uncertainty. There is an option to follow 
                the procedure of Kirkpatrick et al. (2010), fitting only in 
                the 0.9-1.4 micron region``
    :Usage: ``spt,unc = splat.classifyByStandard(sp, \**kwargs)``
    :param sp: ``Spectrum class object, which should contain wave, flux and 
                 noise array elements.``
    :param \**kwargs (optional): - ``'best' = False: return the best fit standard type only``
                        - ``'compareto' = False: compare to a single standard (string or number)``
                        - ``'plot' = False: generate a plot comparing best fit standard to source, can be save to a file using the file keyword``
                        - ``'file' = '': output spectrum plot to a file``
                        - ``'method' = '': set to 'kirkpatrick' to follow the Kirkpatrick et al. (2010) method, fitting only to the 0.9-1.4 micron band``
                        - ``'sptrange' = ['M0','T9']: constraint spectral type range to fit, can be strings or numbers``
                        - ``'string' = True: return spectral type as a string``
                        - ``'verbose' = False: Give lots of feedback``
    :Example:
       >>> import splat
       >>> spc = splat.getSpectrum(shortname='1507-1627')[0]
       >>> print splat.classifyByStandard(spc,string=True,method='kirkpatrick',plot=True)
       ('L4.5', 0.7138959194725174)
    '''
    verbose = kwargs.get('verbose',False)
    method = kwargs.get('method','')
    best_flag = kwargs.get('best',False)
    sptrange = kwargs.get('sptrange',[10,39])
    if (isinstance(sptrange[0],str) != False):
        sptrange = [typeToNum(sptrange[0]),typeToNum(sptrange[1])]
    unc_sys = 0.5

# if you just want to compare to one standard
    cspt = kwargs.get('compareto',False)
    if (cspt != False):
        if (isinstance(cspt,str) == False):
            cspt = typeToNum(cspt)
# round off
        cspt = typeToNum(numpy.round(typeToNum(cspt)))
        mkwargs = copy.deepcopy(kwargs)
        mkwargs['compareto'] = False
        mkwargs['sptrange'] =[cspt,cspt]
        return classifyByStandard(sp,**mkwargs)
            
#    stdsptnum = numpy.arange(30)+10.
#    stdsptstr = ['M'+str(n) for n in numpy.arange(10)]
#    stdsptstr.append(['L'+str(n) for n in numpy.arange(10)])
#    stdsptstr.append(['T'+str(n) for n in numpy.arange(10)])

    if (method == 'kirkpatrick'):
        comprng = [0.9,1.4]*u.micron         # as prescribed in Kirkpatrick et al. 2010, ApJS, 
    else:
        comprng = [0.7,2.45]*u.micron       # by default, compare whole spectrum

# which comparison statistic to use
    if numpy.isnan(numpy.median(sp.noise)):
        compstat = 'stddev_norm'
    else:
        compstat = 'chisqr'

# compute fitting statistics
    stat = []
    sspt = []
    sfile = []
    for t in numpy.arange(sptrange[0],sptrange[1]+1):
        spstd = loadSpectrum(file=spex_stdfiles[typeToNum(t)])
        chisq,scale = compareSpectra(sp,spstd,fit_ranges=[comprng],stat=compstat,novar2=True)
        stat.append(chisq)
        sspt.append(t)
        sfile.append(spex_stdfiles[typeToNum(t)])
        if (verbose):
            print spex_stdfiles[typeToNum(t)], typeToNum(t), chisq, scale

# list of sorted standard files and spectral types
    sorted_stdfiles = [x for (y,x) in sorted(zip(stat,sfile))]
    sorted_stdsptnum = [x for (y,x) in sorted(zip(stat,sspt))]

# select either best match or an ftest-weighted average
    if (best_flag or len(stat) == 1):
        sptn = sorted_stdsptnum[0]
        sptn_e = unc_sys
    else:
        try:
            st = stat.value
        except:
            st = stat
        if numpy.isnan(numpy.median(sp.noise)):
            mean,var = weightedMeanVar(sspt,st)
        else:
            mean,var = weightedMeanVar(sspt,st,method='ftest',dof=sp.dof)        
        if (var**0.5 < 1.):
            sptn = numpy.round(mean*2)*0.5
        else:
            sptn = numpy.round(mean)
        sptn_e = (unc_sys**2+var)**0.5

# string or not?
    if (kwargs.get('string', True) == True):
        spt = typeToNum(sptn,uncertainty=sptn_e)
    else:
        spt = sptn

# plot spectrum compared to best spectrum
    if (kwargs.get('plot',False) != False):
        spstd = loadSpectrum(file=sorted_stdfiles[0])
        chisq,scale = compareSpectra(sp,spstd,fit_ranges=[comprng],stat=compstat)
        spstd.scale(scale)
        plotSpectrum(sp,spstd,colors=['k','r'],\
            title=sp.name+' vs '+typeToNum(sorted_stdsptnum[0])+' Standard',**kwargs)

    return spt, sptn_e
    

def classifyByTemplate(sp, *args, **kwargs):
    '''
    :Purpose: ``Determine the spectral type and uncertainty for a 
                spectrum by direct comparison to a large set of spectra in
                the library. One can select down the spectra by using the set
                command. Returns the best match or an F-test weighted mean and 
                uncertainty. There is an option to follow  the procedure of 
                Kirkpatrick et al. (2010), fitting only in the 0.9-1.4 micron 
                region. ``
    :Usage: ``spt,unc = splat.classifyByTemplate(sp, \*args, \**kwargs)``
    :param sp: ``Spectrum class object, which should contain wave, flux and 
                 noise array elements.``
    :param \**kwargs (optional): - ``'best' = False: return only the best fit template type``
                    - ``'plot' = False: generate a plot comparing best fit standard to source, can be save to a file using the file keyword``
                    - ``'file' = '': output spectrum plot to a file``
                    - ``'method' = '': set to 'kirkpatrick' to follow the Kirkpatrick et al. (2010) method, fitting only to the 0.9-1.4 micron band``
                    - ``'set' = '': string defining which spectral template set you want to compare to; several options which can be combined:``
                        * ``'m dwarf': fit to M dwarfs only``
                        * ``'l dwarf': fit to M dwarfs only``
                        * ``'t dwarf': fit to M dwarfs only``
                        * ``'vlm': fit to M7-T9 dwarfs``
                        * ``'optical': only optical classifications``
                        * ``'high sn': median S/N greater than 100``
                        * ``'young': only young/low surface gravity dwarfs``
                        * ``'companion': only companion dwarfs``
                        * ``'subdwarf': only subdwarfs``
                        * ``'single': only dwarfs not indicated a binaries``
                        * ``'spectral binaries': only dwarfs indicated to be spectral binaries``
                        * ``'standard': only spectral standards (use classifyByStandard instead)``
                    - ``'string' = True: return spectral type as a string``
                    - ``'sptype' = 'spex': specify which spectral classification type to return; can be 'spex', 'opt', 'nir', or 'lit'
                    - ``'verbose' = False: Give lots of feedback``
    :Example:
       >>> import splat
       >>> spc = splat.getSpectrum(shortname='1507-1627')[0]
       >>> print splat.classifyByTemplate(spc,string=True,set='l dwarf, high sn', sptype='spex', plot=True)
       ('L4.5', 0.7138959194725174)
    '''
    sptype = kwargs.get('sptype','spex')
    verbose = kwargs.get('verbose',True)
    set = kwargs.get('set','')
    unc_sys = 0.5
    if (kwargs.get('method','') == 'kirkpatrick'):
        comprng = [0.9,1.4]*u.micron         # as prescribed in Kirkpatrick et al. 2010, ApJS, 
    else:
        comprng = [0.7,2.45]*u.micron       # by default, compare whole spectrum

#  canned searches
#  constrain spectral types
    spt = [10.,39.9]
    if ('m dwarf' in set):
        spt = [10,19.9]
    if ('l dwarf' in set):
        spt = [20,29.9]
    if ('t dwarf' in set):
        spt = [30,39.9]
    if ('vlm' in set):
        spt = [numpy.max([17,spt[0]]),numpy.min([39.9,spt[-1]])]
    spt = kwargs.get('spt',spt)
    
#  constrain S/N
    snr = 0.
    if ('high sn' in set):
        snr = 100.
    snr = kwargs.get('snr',snr)
    
#  don't compare to same spectrum
    try:
        excludefile = [sp.filename]
    except:
        excludefile = ['']
    excludefile = kwargs.get('excludefile',excludefile)
        
    if ('optical' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,opt_type=spt,giant=False,logic='and')
    elif ('standard' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,standard=True,logic='and')
    elif ('companion' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,companion=True,giant=False,logic='and')
    elif ('young' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,young=True,logic='and')
    elif ('subdwarf' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,subdwarf=True,logic='and')
    elif ('single' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,spbinary=False,binary=False,giant=False,logic='and')
    elif ('spectral binaries' in set):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt,spbinary=True,logic='and')
    elif (set != ''):
        lib = searchLibrary(output='all',excludefile=excludefile,snr=snr,spt=spt)
    else:
        lib = searchLibrary(output='all',excludefile=excludefile,**kwargs)
        
# first search for the spectra desired - parameters are set by user
    files = lib['data_file']

# which spectral type to return
    if ('spex' in sptype):
        sptref = 'spex_type'
    elif ('opt' in sptype):
        sptref = 'opt_type'
    elif ('nir' in sptype):
        sptref = 'nir_type'
    else:
        sptref = 'lit_type'

    lib = lib[:][numpy.where(lib[sptref] != '')]
    files = lib['data_file']
    sspt = [typeToNum(s) for s in lib[sptref]]

    if len(files) == 0:
        print '\nNo templates available for comparison\n\n'
        return numpy.nan, numpy.nan
    if (verbose):
        print '\nComparing to {} templates\n\n'.format(len(files))
    if len(files) > 100:
        if (verbose):
            print 'This may take some time!\n\n'.format(len(files))

# do comparison
    stat = []
    for i,f in enumerate(files):
        s = loadSpectrum(file=f)
        chisq,scale = compareSpectra(sp,s,fit_ranges=[comprng],stat='chisqr',novar2=True)
        stat.append(chisq)
        if (verbose):
            print f, typeToNum(sspt[i]), chisq, scale
        
# list of sorted standard files and spectral types
    sorted_files = [x for (y,x) in sorted(zip(stat,files))]
    sorted_spt = [x for (y,x) in sorted(zip(stat,sspt))]

# select either best match or an ftest-weighted average
    if (kwargs.get('best',False) or len(stat) == 1):
        sptn = sorted_spt[0]
        sptn_e = unc_sys
    else:
        mean,var = weightedMeanVar(sspt,stat,method='ftest',dof=sp.dof)
        if (var**0.5 < 1.):
            sptn = numpy.round(mean*2.)*0.5
        else:
            sptn = numpy.round(mean)
        sptn_e = (unc_sys**2+var)**0.5

# plot spectrum compared to best spectrum
    if (kwargs.get('plot',False) != False):
        s = loadSpectrum(file=sorted_files[0])
        chisq,scale = compareSpectra(sp,s,fit_ranges=[comprng],stat='chisqr')
        s.scale(scale)
        plotSpectrum(sp,s,colors=['k','r'],title=sp.name+' vs '+s.name,**kwargs)

# string or not?
    if (kwargs.get('string', True) == True):
        spt = typeToNum(sptn,uncertainty=sptn_e)
    else:
        spt = sptn

    return spt, sptn_e
 

def classifyGravity(sp, *args, **kwargs):
    '''Determine the gravity classification of a brown dwarf
    using the method of Allers & Liu 2013'''
    
    verbose = kwargs.get('verbose',False)
    
# Chart for determining gravity scores based on gravity sensitive 
# indices as described in the Allers and Liu paper.
# The key to the overall indices dictionary is each index name.
# The key to each index dictionary are the spectral types, which 
# contain the limits for each gravity score.
# To access a value do the following: print grav['FeH-z']['M5'][0] 
# which should return 'nan'
    
# Note: alternate method is Canty et al. (2013, MNRAS, 435, 2650)
# H2(K) index: median[2.16-2.18]/median[2.23-2.25]
   
    grav = {\
        'FeH-z':{'M5.0':[numpy.nan,numpy.nan],'M6.0':[1.068,1.039],'M7.0':[1.103,1.056],'M8.0':[1.146,1.074],'M9.0': [1.167,1.086],'L0.0': [1.204,1.106],'L1.0':[1.252,1.121],'L2.0':[1.298,1.142],'L3.0': [1.357,1.163],'L4.0': [1.370,1.164],'L5.0': [1.258,1.138],'L6.0': [numpy.nan,numpy.nan],'L7.0': [numpy.nan,numpy.nan]},\
        'VO-z': {'M5.0':[numpy.nan,numpy.nan],'M6.0':[numpy.nan,numpy.nan],'M7.0': [numpy.nan,numpy.nan],'M8.0': [numpy.nan,numpy.nan],'M9.0': [numpy.nan,numpy.nan],'L0.0': [1.122,1.256],'L1.0': [1.112,1.251],'L2.0': [1.110,1.232],'L3.0': [1.097,1.187],'L4.0': [1.073,1.118],'L5.0': [numpy.nan,numpy.nan],'L6.0': [numpy.nan,numpy.nan],'L7.0': [numpy.nan,numpy.nan]},\
        'KI-J': {'M5.0': [numpy.nan,numpy.nan], 'M6.0': [1.042,1.028], 'M7.0': [1.059,1.036],'M8.0': [1.077,1.046],'M9.0': [1.085,1.053],'L0.0': [1.098,1.061],'L1.0': [1.114,1.067],'L2.0': [1.133,1.073],'L3.0': [1.135,1.075],'L4.0': [1.126,1.072],'L5.0': [1.094,1.061],'L6.0': [numpy.nan,numpy.nan],'L7.0': [numpy.nan,numpy.nan]},\
        'H-cont': {'M5.0': [numpy.nan,numpy.nan], 'M6.0': [.988,.994], 'M7.0': [.981,.990],'M8.0': [.963,.984],'M9.0': [.949,.979],'L0.0': [.935,.972],'L1.0': [.914,.968],'L2.0': [.906,.964],'L3.0': [.898,.960],'L4.0': [.885,.954],'L5.0': [.869,.949],'L6.0': [.874,.950],'L7.0': [numpy.nan,numpy.nan]}}

# Calculate Allers indices and their uncertainties 
    ind = kwargs.get('indices',False)
    if ind == False:
        ind = measureIndexSet(sp,set='allers')

# Determine the object's NIR spectral type and its uncertainty 
    sptn = kwargs.get('spt',False)
    if sptn == False:
        sptn, spt_e = classifyByIndex(sp,string=False,set='allers')
        if numpy.isnan(sptn):
            print 'Spectral type could not be determined from indices'
            return numpy.nan
    if isinstance(sptn,str):
        sptn = typeToNum(sptn)
    Spt = typeToNum(numpy.floor(sptn))

#Check whether the NIR SpT is within gravity sensitive range values
    if ((sptn < 16.0) or (sptn > 27.0)):
        print 'Spectral type '+typeToNum(sptn)+' outside range for gravity classification'
        return numpy.nan

#Creates an empty array with dimensions 4x1 to fill in later with 5 gravscore values
    gravscore = {}
    medgrav = []

# Use the spt to pick the column that contains the 
# values we want to compare our indices with. 
    for k in grav.keys():
        val = 0.0
        if k == 'VO-z' or k=='H-cont':
            if numpy.isnan(grav[k][Spt][0]):
                val = numpy.nan
            if ind[k][0] >= grav[k][Spt][0]:
                val = 1.0
            if ind[k][0] >= grav[k][Spt][1]:
                val = 2.0
            if verbose:
                print k,ind[k][0], ind[k][1], val 
        if k == 'FeH-z' or k=='KI-J':
            if numpy.isnan(grav[k][Spt][0]):
                val = numpy.nan
            if ind[k][0] <= grav[k][Spt][0]:
                val = 1.0
            if ind[k][0] <= grav[k][Spt][1]:
                val = 2.0
            if verbose:
                print k,ind[k][0], ind[k][1], val 
        gravscore[k] = val
        medgrav.append(val)

# determine median score, or mean if even					
    if (len(numpy.where(numpy.isnan(medgrav) == False))%2 == 0):
        gravscore['score'] = scipy.stats.nanmean(medgrav)        
    else:        
        gravscore['score'] = scipy.stats.nanmedian(medgrav)        

    if gravscore['score'] <= 0.5:
       gravscore['gravity_class'] = 'FLD-G'
    elif gravscore['score'] > 0.5 and gravscore['score'] < 1.5:
       gravscore['gravity_class'] = 'INT-G'
    elif gravscore['score'] >= 1.5:
       gravscore['gravity_class'] = 'VL-G'

# plot spectrum against standard
    if (kwargs.get('plot',False) != False):
        spt,unc = classifyByStandard(sp,compareto=Spt,method='kirkpatrick',**kwargs)
        
# return gravity class or entire dictionary
    if (kwargs.get('allscores',False) == False):
        return gravscore['gravity_class']
    else:
        return gravscore

    
    
def compareSpectra(sp1, sp2, *args, **kwargs):
    '''Compare two spectra against each other'''
    weights = kwargs.get('weights',numpy.zeros(len(sp1.wave)))
    mask = kwargs.get('mask',numpy.zeros(len(sp1.wave)))    # mask = 1 -> ignore
    fit_ranges = kwargs.get('fit_ranges',[spex_wave_range])
    mask_ranges = kwargs.get('mask_ranges',[])
    mask_telluric = kwargs.get('mask_telluric',False)
    mask_standard = kwargs.get('mask_standard',False)
    var_flag = kwargs.get('novar2',False)
    stat = kwargs.get('stat','chisqr')
    minreturn = 1.e-9
    if ~isinstance(fit_ranges[0],astropy.units.quantity.Quantity):
        fit_ranges*=u.micron
    
    if (mask_standard == True):
        mask_telluric == True
        
# create interpolation function for second spectrum
    f = interp1d(sp2.wave,sp2.flux,bounds_error=False,fill_value=0.)
    if var_flag:
        v = interp1d(sp2.wave,sp2.variance*numpy.nan,bounds_error=False,fill_value=numpy.nan)
    else:        
        v = interp1d(sp2.wave,sp2.variance,bounds_error=False,fill_value=numpy.nan)
    
# total variance - funny form to cover for nans
    vtot = numpy.nanmax([sp1.variance.value,sp1.variance.value+v(sp1.wave.value)],axis=0)
 #   vtot = sp1.variance
    
# Mask certain wavelengths
# telluric absorption
    if (mask_telluric):
        mask_ranges.append([0.,0.65]*u.micron)        # meant to clear out short wavelengths
        mask_ranges.append([1.35,1.42]*u.micron)
        mask_ranges.append([1.8,1.92]*u.micron)
        mask_ranges.append([2.45,99.]*u.micron)        # meant to clear out long wavelengths

    if (mask_standard):
        mask_ranges.append([0.,0.8]*u.micron)        # standard short cut
        mask_ranges.append([2.35,99.]*u.micron)        # standard long cut

    for ranges in mask_ranges:
        mask[numpy.where(((sp1.wave >= ranges[0]) & (sp1.wave <= ranges[1])))] = 1

# set the weights    
    for ranges in fit_ranges:
        weights[numpy.where(((sp1.wave >= ranges[0]) & (sp1.wave <= ranges[1])))] = 1
     
# mask flux < 0
    mask[numpy.where(numpy.logical_or(sp1.flux < 0,f(sp1.wave) < 0))] = 1

    weights = weights*(1.-mask)

# comparison statistics

# chi^2
    if (stat == 'chisqr'):
# compute scale factor    
        scale = numpy.nansum(weights*sp1.flux.value*f(sp1.wave)/vtot)/ \
            numpy.nansum(weights*f(sp1.wave)*f(sp1.wave)/vtot)
# correct variance
        vtot = numpy.nanmax([sp1.variance.value,sp1.variance.value+v(sp1.wave)*scale**2],axis=0)
        stat = numpy.nansum(weights*(sp1.flux.value-f(sp1.wave)*scale)**2/vtot)
        unit = sp1.funit/sp1.funit

# normalized standard deviation
    elif (stat == 'stddev_norm'):
# compute scale factor    
        scale = numpy.nansum(weights*sp1.flux.value)/ \
            numpy.nansum(weights*f(sp1.wave))
# correct variance
        stat = numpy.nansum(weights*(sp1.flux.value-f(sp1.wave)*scale)**2)/ \
            numpy.median(sp1.flux.value)**2
        unit = sp1.funit/sp1.funit

# standard deviation
    elif (stat == 'stddev'):
# compute scale factor    
        scale = numpy.nansum(weights*sp1.flux.value*f(sp1.wave))/ \
            numpy.nansum(weights*f(sp1.wave)*f(sp1.wave))
# correct variance
        stat = numpy.nansum(weights*(sp1.flux.value-f(sp1.wave)*scale)**2)
        unit = sp1.funit**2

# absolute deviation
    elif (stat == 'absdev'):
# compute scale factor    
        scale = numpy.nansum(weights*sp1.flux.value)/ \
            numpy.nansum(weights*f(sp1.wave))
# correct variance
        stat = numpy.nansum(weights*abs(sp1.flux.value-f(sp1.wave)*scale))
        unit = sp1.funit

# error
    else:
        print 'Error: statistic {} for compareSpectra not available'.format(stat)
        return numpy.nan, numpy.nan

    return numpy.nanmax([stat,minreturn])*unit, scale
        

def coordinateToDesignation(c):
    '''Convert RA, Dec into designation string'''
# input is ICRS
    if isinstance(c,SkyCoord):
        cc = c
    else:
        cc = properCoordinates(c)
# input is [RA,Dec] pair in degrees
    return string.replace('J{0}{1}'.format(cc.ra.to_string(unit=u.hour, sep='', precision=2, pad=True), \
        cc.dec.to_string(unit=u.degree, sep='', precision=1, alwayssign=True, pad=True)),'.','')


def dateToCaldate(d):
    '''Convert from numeric date to calendar date'''
    return d[:4]+' '+months[int(d[5:6])-1]+' '+d[-2:]


def designationToCoordinate(value, **kwargs):
    '''Convert a designation into a RA, Dec tuple or ICRS'''
    icrsflag = kwargs.get('icrs',True)

    a = re.sub('[j.:hms]','',value.lower())
    fact = 1.
    spl = a.split('+')
    if len(spl) == 1:
        spl = a.split('-')
        fact = -1.
    ra = 15.*float(spl[0][0:2])
    if (len(spl[0]) > 2):
        ra+=15.*float(spl[0][2:4])/60.
    if (len(spl[0]) > 4):
        ra+=15.*float(spl[0][4:6])/3600.
    if (len(spl[0]) > 6):
        ra+=15.*float(spl[0][6:8])/360000.
    dec = float(spl[1][0:2])
    if (len(spl[0]) > 2):
        dec+=float(spl[1][2:4])/60.
    if (len(spl[0]) > 4):
        dec+=float(spl[1][4:6])/3600.
    if (len(spl[1]) > 6): 
        dec+=float(spl[1][6:8])/360000.
    dec = dec*fact
    if icrsflag:
        return SkyCoord(ra=ra*u.degree, dec=dec*u.degree, frame='icrs')
    else:
        return [ra,dec]


def designationToShortName(value):
    '''Produce a shortened version of designation'''
    if isinstance(value,str):
        a = re.sub('[j.:hms]','',value.lower())
        mrk = '+'
        spl = a.split(mrk)
        if len(spl) == 1:
            mrk = '-'
            spl = a.split(mrk)
        if len(spl) == 2:
            return 'J'+spl[0][0:4]+mrk+spl[1][0:4]
        else:
            return value
    else:
        raise ValueError('\nMust provide a string value for designation\n\n')

        

def fetchDatabase(*args, **kwargs):    
    '''Get the SpeX Database from either online repository or local drive'''
    dataFile = kwargs.get('dataFile','db_spexprism.txt')
    folder = kwargs.get('folder','~/')
    url = kwargs.get('url',SPLAT_URL)+'/Databases/'
    local = kwargs.get('local',False)

# check if online
    local = local or (not checkOnline())
        
# first try online
    if not local:
        try:
            open(os.path.basename(TMPFILENAME), 'wb').write(urllib2.urlopen(url+dataFile).read())
            data = ascii.read(os.path.basename(TMPFILENAME), delimiter='\t',fill_values='-99.',format='tab')
            os.remove(os.path.basename(TMPFILENAME))
#            return data
        except urllib2.URLError:
            sys.stderr.write('\nReading local '+dataFile+'\n\n')
            local = True
    
# now try local drive - NOT WORKING
    file = dataFile
    if local:
        if (os.path.exists(file) == False):
            file = folder+os.path.basename(file)
        if (os.path.exists(file) == False):
            raise NameError('\nCould not find '+dataFile+' or '+file+' locally\n\n')
        else:
            data = ascii.read(file, delimiter='    ')

# clean up blanks and convert numerical values to numbers
    data['ra'][numpy.where(data['ra'] == '')] = '0.'
#    data['ran'] = [float(x) for x in data['ra']]
    data['dec'][numpy.where(data['dec'] == '')] = '0.'
#    data['decn'] = [float(x) for x in data['dec']]
    data['jmag'][numpy.where(data['jmag'] == '')] = '99.'
#    data['jmagn'] = [float(x) for x in data['jmag']]
    data['hmag'][numpy.where(data['hmag'] == '')] = '99.'
#    data['hmagn'] = [float(x) for x in data['hmag']]
    data['kmag'][numpy.where(data['kmag'] == '')] = '99.'
#    data['kmagn'] = [float(x) for x in data['kmag']]
    data['jmag_error'][numpy.where(data['jmag_error'] == '')] = '99.'
#    data['jmag_errorn'] = [float(x) for x in data['jmag_error']]
    data['hmag_error'][numpy.where(data['hmag_error'] == '')] = '99.'
#    data['hmag_errorn'] = [float(x) for x in data['hmag_error']]
    data['kmag_error'][numpy.where(data['kmag_error'] == '')] = '99.'
#    data['kmag_errorn'] = [float(x) for x in data['kmag_error']]
    data['resolution'][numpy.where(data['resolution'] == '')] = '120'
#    data['resolutionn'] = [float(x) for x in data['resolution']]
    data['airmass'][numpy.where(data['airmass'] == '')] = '1.'
#    data['airmassn'] = [float(x) for x in data['airmass']]
    data['median_snr'][numpy.where(data['median_snr'] == '')] = '0'
#    data['median_snrn'] = [float(x) for x in data['median_snr']]

# convert coordinates to SkyCoord format
#    data['skycoords'] = data['ra']
    s = []
    for i in numpy.arange(len(data['ra'])):
        try:        # to deal with a blank string
            s.append(SkyCoord(ra=float(data['ra'][i])*u.degree,dec=float(data['dec'][i])*u.degree,frame='icrs'))
        except:
            s.append(SkyCoord(ra=0.*u.degree,dec=0.*u.degree,frame='icrs'))
    data['skycoords'] = s

# add in RA/Dec (TEMPORARY)
#    ra = []
#    dec = []
#    for x in data['designation']:
#        c = designationToCoordinate(x,ICRS=False)
#        ra.append(c[0])
#        dec.append(c[1])
#    data['ra'] = ra
#    data['dec'] = dec

    data['young'] = ['young' in x for x in data['library']]
    data['subdwarf'] = ['subdwarf' in x for x in data['library']]
    data['binary'] = ['binary' in x for x in data['library']]
    data['spbinary'] = ['sbinary' in x for x in data['library']]
    data['blue'] = ['blue' in x for x in data['library']]
    data['red'] = ['red' in x for x in data['library']]
    data['giant'] = ['giant' in x for x in data['library']]
    data['wd'] = ['wd' in x for x in data['library']]
    data['standard'] = ['std' in x for x in data['library']]
    data['companion'] = ['companion' in x for x in data['library']]

# add in shortnames
    data['shortname'] = [designationToShortName(x) for x in data['designation']]

# create literature spt 
    data['lit_type'] = data['opt_type']
    w = numpy.where(numpy.logical_and(data['lit_type'] == '',data['nir_type'] != ''))
    data['lit_type'][w] = data['nir_type'][w]
    sptn = [typeToNum(x) for x in data['lit_type']]
    w = numpy.where(numpy.logical_and(sptn > 29.,data['nir_type'] != ''))
    data['lit_type'][w] = data['nir_type'][w]
#    w = numpy.where(numpy.logical_and(data['lit_type'] == '',typeToNum(data['spex_type']) > 17.))
#    data['lit_type'][w] = data['spex_type'][w]

    return data


def filenameToNameDate(filename):
    '''Extract from a SPLAT filename the source name and observation date'''
    ind = filename.rfind('.')
    base = filename[:ind]
    spl = base.split('_')
    if (len(spl) < 2):
        return '', ''
    else:
        name = spl[-2]
        d = spl[-1]
        try:
            float(d)
            date = '20'+d
        except ValueError:
#            print filename+' does not contain a date'
            date = ''
        
        return name, date



def filterMag(sp,filter,*args,**kwargs):
    '''
    :Purpose: ``Determine the photometric magnitude of a source based on the
                spectrum. Spectra are convolved with the filter specified by
                the 'filter' input.  By default this filter is also 
                convolved with a model of Vega to extract Vega magnitudes,
                but the user can also specify AB magnitudes, photon flux or
                energy flux.``
    :Usage: ``mag,unc = splat.filterMag(sp, 'filter name',\*args, \**kwargs)``
    :param sp: ``Spectrum class object, which should contain wave, flux and 
                 noise array elements.``
    :param 'filter mag': ``Name of filter, must be one of the following:``
                    - ``'2MASS J', '2MASS H', '2MASS Ks'``
                    - ``'MKO J', 'MKO H', 'MKO K', MKO Kp', 'MKO Ks'``
                    - ``'NICMOS F090M', 'NICMOS F095N', 'NICMOS F097N', 'NICMOS F108N',`` 
                    - ``'NICMOS F110M', 'NICMOS F110W', 'NICMOS F113N', 'NICMOS F140W',``
                    - ``'NICMOS F145M', 'NICMOS F160W', 'NICMOS F164N', 'NICMOS F165M',``
                    - ``'NICMOS F166N', 'NICMOS F170M', 'NICMOS F187N', 'NICMOS F190N'``
                    - ``'NIRC2 J', 'NIRC2 H', 'NIRC2 Kp', 'NIRC2 Ks'``
                    - ``'WIRC J', 'WIRC H', 'WIRC K', 'WIRC CH4S', 'WIRC CH4L'``
                    - ``'WIRC CO', 'WIRC PaBeta', 'WIRC BrGamma', 'WIRC Fe2'``
    :param \**kwargs (optional): - ``'info' = False: give the filter names available``
                    - ``'custom' = False: specify to a 2 x N vector array specifying the wavelengths and transmissions for a custom filter``
                    - ``'ab' = False: compute AB magnitudes``
                    - ``'vega' = True: compute Vega magnitudes``
                    - ``'energy' = False: compute energy flux``
                    - ``'photon' = False: compute photon flux``
                    - ``'filterFolder' = '': folder containing the filter transmission files``
                    - ``'vegaFile' = '': name of file containing Vega flux file, must be within 'filterFolder'``
                    - ``'nsamples' = 100: number of samples to use in MC error estimation``
    :Example:
       >>> import splat
       >>> spc = splat.getSpectrum(shortname='1507-1627')[0]
       >>> spc.fluxCalibrate('2MASS J',14.5)
       >>> print splat.filterMag(spc,'MKO J')
       (14.345894376898123, 0.027596454828421831)
    '''
# keyword parameters
    filterFolder = kwargs.get('filterFolder',SPLAT_PATH+FILTER_FOLDER)
    if not os.path.exists(filterFolder):
        filterFolder = SPLAT_URL+FILTERFOLDER
    vegaFile = kwargs.get('vegaFile','vega_kurucz.txt')
    info = kwargs.get('info',False)
    custom = kwargs.get('custom',False)
    vega = kwargs.get('vega',True)
    ab = kwargs.get('ab',False)
    photons = kwargs.get('photons',False)
    energy = kwargs.get('energy',False)
    nsamples = kwargs.get('nsamples',100)

# filter file assignments
    filters = { \
        '2MASS J': {'file': 'j_2mass.txt', 'description': '2MASS J-band'}, \
        '2MASS H': {'file': 'h_2mass.txt', 'description': '2MASS H-band'}, \
        '2MASS Ks': {'file': 'ks_2mass.txt', 'description': '2MASS Ks-band'}, \
        'MKO J': {'file': 'j_atm_mko.txt', 'description': 'MKO J-band + atmosphere'}, \
        'MKO H': {'file': 'h_atm_mko.txt', 'description': 'MKO H-band + atmosphere'}, \
        'MKO K': {'file': 'k_atm_mko.txt', 'description': 'MKO K-band + atmosphere'}, \
        'MKO Kp': {'file': 'mko_kp.txt', 'description': 'MKO Kp-band'}, \
        'MKO Ks': {'file': 'mko_ks.txt', 'description': 'MKO Ks-band'}, \
        'NICMOS F090M': {'file': 'nic1_f090m.txt', 'description': 'NICMOS F090M'}, \
        'NICMOS F095N': {'file': 'nic1_f095n.txt', 'description': 'NICMOS F095N'}, \
        'NICMOS F097N': {'file': 'nic1_f097n.txt', 'description': 'NICMOS F097N'}, \
        'NICMOS F108N': {'file': 'nic1_f108n.txt', 'description': 'NICMOS F108N'}, \
        'NICMOS F110M': {'file': 'nic1_f110m.txt', 'description': 'NICMOS F110M'}, \
        'NICMOS F110W': {'file': 'nic1_f110w.txt', 'description': 'NICMOS F110W'}, \
        'NICMOS F113N': {'file': 'nic1_f113n.txt', 'description': 'NICMOS F113N'}, \
        'NICMOS F140W': {'file': 'nic1_f140w.txt', 'description': 'NICMOS F140W'}, \
        'NICMOS F145M': {'file': 'nic1_f145m.txt', 'description': 'NICMOS F145M'}, \
        'NICMOS F160W': {'file': 'nic1_f160w.txt', 'description': 'NICMOS F160W'}, \
        'NICMOS F164N': {'file': 'nic1_f164n.txt', 'description': 'NICMOS F164N'}, \
        'NICMOS F165M': {'file': 'nic1_f165m.txt', 'description': 'NICMOS F165M'}, \
        'NICMOS F166N': {'file': 'nic1_f166n.txt', 'description': 'NICMOS F166N'}, \
        'NICMOS F170M': {'file': 'nic1_f170m.txt', 'description': 'NICMOS F170M'}, \
        'NICMOS F187N': {'file': 'nic1_f187n.txt', 'description': 'NICMOS F187N'}, \
        'NICMOS F190N': {'file': 'nic1_f190n.txt', 'description': 'NICMOS F190N'}, \
        'NIRC2 J': {'file': 'nirc2-j.txt', 'description': 'NIRC2 J-band'}, \
        'NIRC2 H': {'file': 'nirc2-h.txt', 'description': 'NIRC2 H-band'}, \
        'NIRC2 Kp': {'file': 'nirc2-kp.txt', 'description': 'NIRC2 Kp-band'}, \
        'NIRC2 Ks': {'file': 'nirc2-ks.txt', 'description': 'NIRC2 Ks-band'}, \
        'WIRC J': {'file': 'wirc_jcont.txt', 'description': 'WIRC J-cont'}, \
        'WIRC H': {'file': 'wirc_hcont.txt', 'description': 'WIRC H-cont'}, \
        'WIRC K': {'file': 'wirc_kcont.txt', 'description': 'WIRC K-cont'}, \
        'WIRC CO': {'file': 'wirc_co.txt', 'description': 'WIRC CO'}, \
        'WIRC CH4S': {'file': 'wirc_ch4s.txt', 'description': 'WIRC CH4S'}, \
        'WIRC CH4L': {'file': 'wirc_ch4l.txt', 'description': 'WIRC CH4L'}, \
        'WIRC Fe2': {'file': 'wirc_feii.txt', 'description': 'WIRC Fe II'}, \
        'WIRC BrGamma': {'file': 'wirc_brgamma.txt', 'description': 'WIRC H I Brackett Gamma'}, \
        'WIRC PaBeta': {'file': 'wirc_pabeta.txt', 'description': 'WIRC H I Paschen Beta'} \
        }

# check that requested filter is in list
    if (filter not in filters.keys()):
        print 'Filter '+filter+' not included in filterMag'
        info = True
        
# print out what's available
    if (info):
        print 'Filter names:'
        for x in filters.keys():
            print x+': '+filters[x]['description']    
        return numpy.nan, numpy.nan

# Read in filter
    if (custom == False):
        fwave,ftrans = numpy.genfromtxt(filterFolder+filters[filter]['file'], comments='#', unpack=True, \
            missing_values = ('NaN','nan'), filling_values = (numpy.nan))
    else:
        fwave,ftrans = custom[0],custom[1]
    fwave = fwave[~numpy.isnan(ftrans)]*u.micron   # temporary fix
    ftrans = ftrans[~numpy.isnan(ftrans)]
                
# interpolate spectrum onto filter wavelength function
    wgood = numpy.where(~numpy.isnan(sp.noise))
    if len(sp.wave[wgood]) > 0:
        d = interp1d(sp.wave[wgood],sp.flux[wgood],bounds_error=False,fill_value=0.)
        n = interp1d(sp.wave[wgood],sp.noise[wgood],bounds_error=False,fill_value=numpy.nan)
# catch for models
    else:
        print 'no good points'
        d = interp1d(sp.wave,sp.flux,bounds_error=False,fill_value=0.)
        n = interp1d(sp.wave,sp.flux*1.e-9,bounds_error=False,fill_value=numpy.nan)
        
    result = []
    if (vega):
# Read in Vega spectrum
        vwave,vflux = numpy.genfromtxt(filterFolder+vegaFile, comments='#', unpack=True, \
            missing_values = ('NaN','nan'), filling_values = (numpy.nan))
        vwave = vwave[~numpy.isnan(vflux)]*u.micron
        vflux = vflux[~numpy.isnan(vflux)]*(u.erg/(u.cm**2 * u.s * u.micron))
        vflux.to(sp.funit,equivalencies=u.spectral_density(vwave))
# interpolate Vega onto filter wavelength function
        v = interp1d(vwave,vflux,bounds_error=False,fill_value=0.)
        for i in numpy.arange(nsamples):
#            result.append(-2.5*numpy.log10(trapz(ftrans*numpy.random.normal(d(fwave),n(fwave))*sp.funit,fwave)/trapz(ftrans*v(fwave)*sp.funit,fwave)))
            result.append(-2.5*numpy.log10(trapz(ftrans*(d(fwave)+numpy.random.normal(0,1.)*n(fwave))*sp.funit,fwave)/trapz(ftrans*v(fwave)*sp.funit,fwave)))
    if (energy or photons):
        for i in numpy.arange(nsamples):
#            result.append(trapz(ftrans*numpy.random.normal(d(fwave),n(fwave))*sp.funit,fwave))
            result.append(trapz(ftrans*(d(fwave)+numpy.random.normal(0,1.)*n(fwave))*sp.funit,fwave))
        if (photons):
            convert = const.h.to('erg s')*const.c.to('micron/s')
            result = result/convert.value
    if (ab):
        fnu = fwave.to('Hz',equivalencies=u.spectral())
        fconst = 3631*u.jansky
        fconst = fconst.to(sp.fnunit,equivalencies=u.spectral())
        d = interp1d(sp.nu,sp.fnu,bounds_error=False,fill_value=0.)
        n = interp1d(sp.nu,sp.noise,bounds_error=False,fill_value=0.)
        b = trapz((ftrans/fnu)/fconst,fnu)
        for i in numpy.arange(nsamples):
            a = trapz(ftrans*(d(fnu)+numpy.random.normal(0,1)*n(fnu))*sp.fnunit/fnu,fnu)
            result.append(-2.5*numpy.log10(a/b))

    val = numpy.nanmean(result)
    err = numpy.nanstd(result)
    if len(sp.wave[wgood]) == 0:
        err = 0.
    return val,err


def getSpectrum(*args, **kwargs):
    '''
    :Purpose: ``Gets a spectrum from the SPLAT library using various selection criteria.``
    :Usage: ``[sp] = splat.getSpectrum({search commands},**kwargs)``
    :param [sp]: ``array of Spectrum class objects, each of which should contain wave, flux and 
                 noise array elements.``
    :param '{search commands}': ``Various search commands to winnow down the selection:
                    - **name**: search by source name (e.g., name='Gliese 570D')
                    - **shortname**: search be short name (e.g. shortname = 'J1457-2124')
                    - **designation**: search by full designation (e.g., designation = 'J11040127+1959217')
                    - **coordinate**: search around a coordinate by a radius specified by radius keyword (e.g., coordinate=[180.,+30.], radius=10.)
                    - **radius** = 10.: search radius in arcseconds for coordinate search
                    - **spt** or **spex_spt**: search by SpeX spectral type; single value is exact, two-element array gives range (e.g., spt = 'M7' or spt = [24,39])
                    - **opt_spt**: same as spt for literature optical spectral types
                    - **nir_spt**: same as spt for literature NIR spectral types
                    - **jmag, hmag, kmag**: select based on faint limit or range of J, H or Ks magnitudes (e.g., jmag = [12,15])
                    - **snr**: search on minimum or range of S/N ratios (e.g., snr = 30. or snr = [50.,100.])
                    - **young, subdwarf, binary, spbinary, red, blue, giant, wd, standard**: classes to search on (e.g., young=True)
                    - **logic** or **combine** = 'and': search logic, can be 'and' or 'or'
                    - **combine**: same as logic
                    - **date**: search by date (e.g., date = '20040322') or range of dates (e.g., date=[20040301,20040330])
                    - **reference**: search by list of references (bibcodes) (e.g., reference='2011ApJS..197...19K')
    :param \**kwargs (optional): 
                    - **sort** = True: sort results based on Right Ascension
                    - **list** = False: if True, return just a list of the data files (can be done with searchLibrary as well)
                    - **lucky** = False: if True, return one randomly selected spectrum from the selected sample
    :Example:
       >>> import splat
       >>> sp = splat.getSpectrum(shortname='1507-1627')[0]

          Retrieving 1 file

       >>> sparr = splat.getSpectrum(spt='M7')

          Retrieving 120 files

       >>> sparr = splat.getSpectrum(spt='T5',young=True)

		  No files match search criteria
		  
    '''

    result = []
    kwargs['output'] = 'all'
    search = searchLibrary(*args, **kwargs)

# limit access to most users
    if checkAccess() == False:
        search = search[:][numpy.where(search['public'] == 'Y')]
    
    files = search['data_file']
        
# return just the filenames
    if (kwargs.get('list',False) != False):
        return files
    
    if len(files) > 0:
        if (len(files) == 1):
            print '\nRetrieving 1 file\n'
            result.append(loadSpectrum(files[0],header=search[0]))
        else:
        	if (kwargs.get('lucky',False) == True):
	            print '\nRetrieving 1 lucky file\n'
	            ind = random.choice(range(len(files)))
	            result.append(loadSpectrum(files[ind],header=search[ind]))
	        else:
				print '\nRetrieving {} files\n'.format(len(files))
				for i,x in enumerate(files):
					result.append(loadSpectrum(x,header=search[i:i+1]))
        	
    else:
        if checkAccess() == False:
            sys.stderr.write('\nNo published files match search criteria\n\n')
        else:
            sys.stderr.write('\nNo files match search criteria\n\n')

    return result
        


# simple number checker
def isNumber(s):
    '''check if something is a number'''
    try:
        t = float(s)
        return (True and ~numpy.isnan(t))
    except ValueError:
        return False


def loadInterpolatedModel_NEW(*args,**kwargs):


# path to model
#    kwargs['path'] = kwargs.get('path',SPLAT_PATH+SPECTRAL_MODEL_FOLDER)
#    if not os.path.exists(kwargs['path']):
#        kwargs['remote'] = True
#        kwargs['path'] = SPLAT_URL+SPECTRAL_MODEL_FOLDER        
#    kwargs['set'] = kwargs.get('set','BTSettl2008')
#    kwargs['model'] = True
#    for ms in MODEL_PARAMETER_NAMES:
#        kwargs[ms] = kwargs.get(ms,MODEL_PARAMETERS[ms])

# first get model parameters
    pfile = 'parameters_new.txt'
#    parameters = loadModelParameters(**kwargs)

# read in parameters of available models
    folder = SPLAT_PATH+SPECTRAL_MODEL_FOLDER+kwargs['set']+'/'
    if not checkLocal(folder):
        raise NameError('\n\nCould not locate spectral model folder {} locally\n'.format(folder))
    if not checkLocal(folder+pfile):
        raise NameError('\n\nCould not locate parameter list {} locally\n'.format(folder+pfile))
    parameters = ascii.read(folder+pfile)
#    numpy.genfromtxt(folder+pfile, comments='#', unpack=False, \
#        missing_values = ('NaN','nan'), filling_values = (numpy.nan)).transpose()

 
# check that given parameters are in range
    for ms in MODEL_PARAMETER_NAMES[0:3]:
        if (float(kwargs[ms]) < min(parameters[ms]) or float(kwargs[ms]) > max(parameters[ms])):
            raise NameError('\n\nInput value for {} = {} out of range for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))
    for ms in MODEL_PARAMETER_NAMES[3:7]:
        if (kwargs[ms] not in parameters[ms]):
            raise NameError('\n\nInput value for {} = {} not one of the options for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))

# now identify grid points around input parameters
# first set up a mask for digital parameters
    mask = numpy.ones(len(parameters[MODEL_PARAMETER_NAMES[0]]))
    for ms in MODEL_PARAMETER_NAMES[3:7]:
        m = [1 if a == kwargs[ms] else 0 for a in parameters[ms]]
        mask = mask*m
    
# identify grid points around input parameters
# 3x3 grid for teff, logg, z
# note interpolation and model ranges are separate
    dist = numpy.zeros(len(parameters[MODEL_PARAMETER_NAMES[0]]))
    for ms in MODEL_PARAMETER_NAMES[0:3]:
# first get step size
        ps = list(set(parameters[ms]))
        ps.sort()
        pps = numpy.abs(ps-ps[int(0.5*len(ps))])
        pps.sort()
        step = pps[1]
        dist = dist + ((kwargs[ms]-parameters[ms])/step)**2

# apply digital constraints
    ddist = dist/mask    

# find "closest" models
    mvals = {}
    for ms in MODEL_PARAMETER_NAMES[0:3]:
        mvals[ms] = [x for (y,x) in sorted(zip(ddist,parameters[ms]))]


# this is a guess as to how many models we need to get unique parameter values
    nmodels = 12
    mx,my,mz = numpy.meshgrid(mvals[MODEL_PARAMETER_NAMES[0]][0:nmodels],mvals[MODEL_PARAMETER_NAMES[1]][0:nmodels],mvals[MODEL_PARAMETER_NAMES[2]][0:nmodels])
    mkwargs = kwargs.copy()

    for i,w in enumerate(numpy.zeros(nmodels)):
        for ms in MODEL_PARAMETER_NAMES[0:3]:
            mkwargs[ms] = mvals[ms][i]
            print mvals[ms][i]
        mdl = loadModel(**mkwargs)
        if i == 0:
            mdls = numpy.log10(mdl.flux.value)
        else:
            mdls = numpy.column_stack((mdls,numpy.log10(mdl.flux.value)))
            
#
#
#            
## THIS NEXT PART IS BROKEN!
#
#
#
    mflx = numpy.zeros(len(mdl.wave))
    for i,w in enumerate(mflx):
        print i, (mdls[i],) 
        mflx[i] = 10.**(griddata((mx.flatten(),my.flatten(),mz.flatten()),(mdls[i],),\
            (float(kwargs[MODEL_PARAMETER_NAMES[0]]),float(kwargs[MODEL_PARAMETER_NAMES[1]]),\
            float(kwargs[MODEL_PARAMETER_NAMES[2]])),'linear'))
    
    return Spectrum(wave=mdl.wave,flux=mflx*mdl.funit,**kwargs)




def loadInterpolatedModel(*args,**kwargs):
# attempt to generalize models to extra dimensions
    kwargs['url'] = kwargs.get('url',SPLAT_URL+'/Models/')
    kwargs['set'] = kwargs.get('set','BTSettl2008')
    kwargs['model'] = True
    kwargs['local'] = kwargs.get('local',False)
    for ms in MODEL_PARAMETER_NAMES:
        kwargs[ms] = kwargs.get(ms,MODEL_PARAMETERS[ms])

# first get model parameters
    parameters = loadModelParameters(**kwargs)
    
# check that given parameters are in range
    for ms in MODEL_PARAMETER_NAMES[0:3]:
        if (float(kwargs[ms]) < parameters[ms][0] or float(kwargs[ms]) > parameters[ms][1]):
            raise NameError('\n\nInput value for {} = {} out of range for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))
    for ms in MODEL_PARAMETER_NAMES[3:6]:
        if (kwargs[ms] not in parameters[ms]):
            raise NameError('\n\nInput value for {} = {} not one of the options for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))

# identify grid points around input parameters
# 3x3 grid for teff, logg, z
# note interpolation and model ranges are separate
    mrng = []
    rng = []
    for ms in MODEL_PARAMETER_NAMES[0:3]:
        s = float(kwargs[ms]) - float(kwargs[ms])%float(parameters[ms][2])
        r = [max(float(parameters[ms][0]),s),min(s+float(parameters[ms][2]),float(parameters[ms][1]))]
        m = copy.deepcopy(r)
#        print s, r, s-float(kwargs[ms])
        if abs(s-float(kwargs[ms])) < (1.e-3)*float(parameters[ms][2]):
            if float(kwargs[ms])%float(parameters[ms][2])-0.5*float(parameters[ms][2]) < 0.:
                m[1]=m[0]
                r[1] = r[0]+1.e-3*float(parameters[ms][2])
            else:
                m[0] = m[1]
                r[0] = r[1]-(1.-1.e-3)*float(parameters[ms][2])
#        print s, r, m, s-float(kwargs[ms])
        rng.append(r)
        mrng.append(m)
#        print s, r, m
    mx,my,mz = numpy.meshgrid(rng[0],rng[1],rng[2])
    mkwargs = kwargs.copy()

# read in models
# note the complex path is to minimize model reads
    mkwargs['teff'] = mrng[0][0]
    mkwargs['logg'] = mrng[1][0]
    mkwargs['z'] = mrng[2][0]
    md111 = loadModel(**mkwargs)

    mkwargs['z'] = mrng[2][1]
    if (mrng[2][1] != mrng[2][0]):
        md112 = loadModel(**mkwargs)
    else:
        md112 = md111

    mkwargs['logg'] = mrng[1][1]
    mkwargs['z'] = mrng[2][0]
    if (mrng[1][1] != mrng[1][0]):
        md121 = loadModel(**mkwargs)
    else:
        md121 = md111

    mkwargs['z'] = mrng[2][1]
    if (mrng[2][1] != mrng[2][0]):
        md122 = loadModel(**mkwargs)
    else:
        md122 = md121

    mkwargs['teff'] = mrng[0][1]
    mkwargs['logg'] = mrng[1][0]
    mkwargs['z'] = mrng[2][0]
    if (mrng[0][1] != mrng[0][0]):
        md211 = loadModel(**mkwargs)
    else:
        md211 = md111

    mkwargs['z'] = mrng[2][1]
    if (mrng[2][1] != mrng[2][0]):
        md212 = loadModel(**mkwargs)
    else:
        md212 = md112

    mkwargs['logg'] = mrng[1][1]
    mkwargs['z'] = mrng[2][0]
    if (mrng[1][1] != mrng[1][0]):
        md221 = loadModel(**mkwargs)
    else:
        md221 = md211

    mkwargs['z'] = mrng[2][1]
    if (mrng[2][1] != mrng[2][0]):
        md222 = loadModel(**mkwargs)
    else:
        md222 = md221

    mflx = numpy.zeros(len(md111.wave))
    val = numpy.zeros([2,2,2])
    for i,w in enumerate(md111.wave):
        val = numpy.array([ \
            [[numpy.log10(md111.flux.value[i]),numpy.log10(md112.flux.value[i])], \
            [numpy.log10(md121.flux.value[i]),numpy.log10(md122.flux.value[i])]], \
            [[numpy.log10(md211.flux.value[i]),numpy.log10(md212.flux.value[i])], \
            [numpy.log10(md221.flux.value[i]),numpy.log10(md222.flux.value[i])]]])
        mflx[i] = 10.**(griddata((mx.flatten(),my.flatten(),mz.flatten()),val.flatten(),\
            (float(kwargs['teff']),float(kwargs['logg']),float(kwargs['z'])),'linear'))
    
    return Spectrum(wave=md111.wave,flux=mflx*md111.funit,**kwargs)


def loadModel(*args, **kwargs):
    '''load up a model spectrum based on parameters'''

# path to model and set local/online
# by default assume models come from local splat directory
    local = kwargs.get('local',True)
    online = kwargs.get('online',not local and checkOnline())
    kwargs['folder'] = kwargs.get('folder',SPECTRAL_MODEL_FOLDER)
    local = not online
    kwargs['local'] = local
    kwargs['online'] = online
    kwargs['model'] = True


# a filename has been passed - assume this file is a local file
# and check that the path is correct if its fully provided
# otherwise assume path is inside model set folder
    if (len(args) > 0):
        kwargs['filename'] = args[0]
        if not os.path.exists(kwargs['filename']):
            kwargs['filename'] = kwargs['folder']+os.path.basename(kwargs['filename'])
            if not os.path.exists(kwargs['filename']):
                raise NameError('\nCould not find model file {} or {}'.format(kwargs['filename'],kwargs['folder']+os.path.basename(kwargs['filename'])))
            else:
                return Spectrum(**kwargs)
        else:
            return Spectrum(**kwargs)

# set up the model set
    kwargs['set'] = kwargs.get('set','BTSettl2008')

# preset defaults
    for ms in MODEL_PARAMETER_NAMES:
        kwargs[ms] = kwargs.get(ms,MODEL_PARAMETERS[ms])

# some special defaults
    if kwargs['set'] == 'morley12':
        if kwargs['fsed'] == 'nc':
            kwargs['fsed'] = 'f2'
    if kwargs['set'] == 'morley14':
        if kwargs['fsed'] == 'nc':
            kwargs['fsed'] = 'f5'
        if kwargs['cld'] == 'nc':
            kwargs['cld'] = 'f50'


# check that folder/set is present either locally or online
# if not present locally but present online, switch to this mode
# if not present at either raise error
    if not checkLocal(kwargs['folder']+kwargs['set']):
        if not checkOnline(kwargs['folder']+kwargs['set']):
            raise NameError('\nCould not find '+kwargs['folder']+kwargs['set']+' locally or on SPLAT website\n\n')
        else:
            kwargs['local'] = False
            kwargs['online'] = True

# generate model filename
    kwargs['filename'] = kwargs['set']+'_{:.0f}_{:.1f}_{:.1f}_{}_{}_{}_{:.1f}.txt'.\
        format(float(kwargs['teff']),float(kwargs['logg']),float(kwargs['z'])-0.001,kwargs['fsed'],kwargs['cld'],kwargs['kzz'],float(kwargs['slit']))

# get model parameters
#        parameters = loadModelParameters(**kwargs)
#        kwargs['path'] = kwargs.get('path',parameters['path'])
# check that given parameters are in range
#        for ms in MODEL_PARAMETER_NAMES[0:3]:
#            if (float(kwargs[ms]) < parameters[ms][0] or float(kwargs[ms]) > parameters[ms][1]):
#                raise NameError('\n\nInput value for {} = {} out of range for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))
#        for ms in MODEL_PARAMETER_NAMES[3:6]:
#            if (kwargs[ms] not in parameters[ms]):
#                raise NameError('\n\nInput value for {} = {} not one of the options for model set {}\n'.format(ms,kwargs[ms],kwargs['set']))

# check if file is present; if so, read it in, otherwise go to interpolated
# online:
    if kwargs['online']:
        if not checkOnline(kwargs['filename']):
            kwargs['filename'] = kwargs['folder']+kwargs['set']+'/'+kwargs['filename']
        if not checkOnline(kwargs['filename']):
            return loadInterpolatedModel(**kwargs)
        try:
            ftype = kwargs['filename'].split('.')[-1]
            tmp = TMPFILENAME+'.'+ftype
            open(os.path.basename(tmp), 'wb').write(urllib2.urlopen(SPLAT_URL+kwargs['filename']).read()) 
            kwargs['filename'] = os.path.basename(tmp)
            sp = Spectrum(**kwargs)
            os.remove(os.path.basename(tmp))
#               os.close(kwargs['filename'])
            return sp
        except urllib2.URLError:
            raise NameError('\nProblem reading in '+kwargs['set']+'/'+kwargs['filename']+' from SPLAT website\n\n')

# locally:
    else:
        if not checkLocal(kwargs['filename']):
            kwargs['filename'] = kwargs['folder']+kwargs['set']+'/'+kwargs['filename']
        if not checkLocal(kwargs['filename']):
            return loadInterpolatedModel(**kwargs)
        kwargs['filename'] = SPLAT_PATH+kwargs['filename']
        return Spectrum(**kwargs)



def loadModelParameters(**kwargs):
    '''Load up model parameters and check model inputs'''
# keyword parameters
    pfile = kwargs.get('parameterFile','parameters.txt')

# legitimate model set?
    if kwargs.get('set',False) not in DEFINED_MODEL_SET:
        raise NameError('\n\nInput model set {} not in defined set of models:\n{}\n'.format(set,DEFINED_MODEL_SET))
    

# read in parameter file - local and not local
    if kwargs.get('online',False):
        try:
            open(os.path.basename(TMPFILENAME), 'wb').write(urllib2.urlopen(SPLAT_URL+SPECTRAL_MODEL_FOLDER+kwargs['set']+'/'+pfile).read())
            p = ascii.read(os.path.basename(TMPFILENAME))
            os.remove(os.path.basename(TMPFILENAME))
        except urllib2.URLError:
            print '\n\nCannot access online models for model set {}\n'.format(set)
            local = True
    else:            
        if (os.path.exists(pfile) == False):
            pfile = SPLAT_PATH+SPECTRAL_MODEL_FOLDER+kwargs['set']+'/'+os.path.basename(pfile)
            if (os.path.exists(pfile) == False):
                raise NameError('\nCould not find parameter file {}'.format(pfile))
            else:
                p = ascii.read(pfile)


# populate output parameter structure
    parameters = {'set': set, 'url': SPLAT_URL}
    for ms in MODEL_PARAMETER_NAMES[0:3]:
        if ms in p.colnames:
            parameters[ms] = [float(x) for x in p[ms]]
        else:
            raise ValueError('\n\nModel set {} does not have defined parameter range for {}'.format(set,ms))
    for ms in MODEL_PARAMETER_NAMES[3:6]:
        if ms in p.colnames:
            parameters[ms] = str(p[ms][0]).split(",")
        else:
            raise ValueError('\n\nModel set {} does not have defined parameter list for {}'.format(set,ms))

    return parameters


def loadSpectrum(*args, **kwargs):
    '''load up a SpeX spectrum based name, shortname and/or date'''
# keyword parameters
#    name = kwargs.get('name','')
#    shname = kwargs.get('shname','')
#    date = kwargs.get('date','')
    local = kwargs.get('local',False)
    folder = kwargs.get('folder','')
#    header = kwargs.get('header',False)
#    kwargs['header'] = header
    url = kwargs.get('folder',SPLAT_URL+'/Spectra/')
    kwargs['model'] = False
    file = kwargs.get('filename','')
    file = kwargs.get('file',file)
    if (len(args) > 0):
        file = args[0]
    kwargs['filename'] = file

# check if online
    local = local or (not checkOnline())
    
# CODE NEEDED HERE TO SET UP FILE NAME; FOR NOW JUST ERROR
    
# a filename has been passed
    if (kwargs['filename'] == ''):
        raise NameError('\nNeed to pass in filename for spectral data')

# first try online
    if not local:
        try:
#            ftype = file.split('.')[-1]
#            tmp = TMPFILENAME+'.'+ftype
            open(os.path.basename(file), 'wb').write(urllib2.urlopen(url+file).read())
            kwargs['filename'] = os.path.basename(file)
#            if kwargs['header'] == False:
#                kwargs['header'] = searchLibrary(file=kwargs['filename'])
            sp = Spectrum(**kwargs)
            os.remove(os.path.basename(file))
            return sp
        except urllib2.URLError:
            sys.stderr.write('\nCould not find data file '+kwargs['filename']+' at '+url+'\n\n')
            local = True
    
# now try local drive
    if (os.path.exists(kwargs['filename']) == False):
        kwargs['filename'] = folder+os.path.basename(kwargs['filename'])
        if (os.path.exists(kwargs['filename']) == False):
            raise NameError('\nCould not find '+kwargs['filename']+' locally\n\n')
        else:
            return Spectrum(**kwargs)
    else:
        return Spectrum(**kwargs)


#Takes the apparent magnitude and either takes or determines the absolute magnitude, then uses the magnitude/distance relation to estimate the distance to the object in parsecs
#Note: the input spectra should be flux calibrated to their empirical apparent magnitudes

def estimateDistance(sp, **kwargs):
    mag = kwargs.get('mag', False)
    mag_unc = kwargs.get('mag_unc', 0.)
    absmag = kwargs.get('absmag', False)
    absmag_unc = kwargs.get('absmag_unc', 0.)
    spt = kwargs.get('spt', False)
    spt_unc = kwargs.get('spt_e', 0.)
    nsamples = kwargs.get('nsamples', 100)
    filt = kwargs.get('filter', False)

# if no apparent magnitude then calculate from spectrum
    if (mag == False):
        if (filt == False):
            sys.stderr.write('\nPlease specify the filter used to determine the apparent magnitude\n')
            return numpy.nan, numpy.nan
        mag, mag_unc = filterMag(sp,filt)

# if no spt then calculate from spectrum
    if spt == False:
        spt, spt_unc = classifyByIndex(sp)


# if no absolute magnitude then estimate from spectral type
    if absmag == False:
        if filt == False:
            sys.stderr.write('\nPlease specify the filter used to determine the absolute magnitude\n')
            return numpy.nan, numpy.nan
        absmag, absmag_unc = typeToMag(spt,filt,unc=spt_unc)

# create Monte Carlo sets
    if mag_unc > 0.:
        mags = numpy.random.normal(mag, mag_unc, nsamples)
    else:
        mags = nsamples*[mag]

    if absmag_unc > 0.:
        absmags = numpy.random.normal(absmag, absmag_unc, nsamples)
    else:
        absmags = nsamples*[absmag]
 
# calculate 
    distances = 10.**(numpy.subtract(mags,absmags)/5. + 1.)
    d = numpy.mean(distances)
    unc = numpy.std(distances)
    
    return d, unc


# code to measure a defined index from a spectrum using Monte Carlo noise estimate
# measure method can be mean, median, integrate
# index method can be ratio = 1/2, valley = 1-2/3, OTHERS
# output is index value and uncertainty
def measureIndex(sp,*args,**kwargs):
    '''Measure an index on a spectrum based on defined methodology'''

# keyword parameters
    method = kwargs.get('method','ratio')
    sample = kwargs.get('sample','integrate')
    nsamples = kwargs.get('nsamples',100)
    noiseFlag = kwargs.get('nonoise',False)
            
# create interpolation functions
    w = numpy.where(numpy.isnan(sp.flux) == False)
    f = interp1d(sp.wave.value[w],sp.flux.value[w],bounds_error=False,fill_value=0.)
    w = numpy.where(numpy.isnan(sp.noise) == False)
# note that units are stripped out
    if (numpy.size(w) != 0):
        s = interp1d(sp.wave.value[w],sp.noise.value[w],bounds_error=False,fill_value=numpy.nan)
        noiseFlag = False
    else:
        s = interp1d(sp.wave,sp.noise,bounds_error=False,fill_value=numpy.nan)
        noiseFlag = True
                
# error checking on number of arguments provided
    if (len(args) < 2):
        print 'measureIndex needs at least two samples to function'
        return numpy.nan, numpy.nan
    elif (len(args) < 3 and (method == 'line' or method == 'allers')):
        print method+' requires at least 3 sample regions'
        return numpy.nan, numpy.nan

# define the sample vectors
    values = numpy.zeros((len(args),nsamples))

# loop over all sampling regions
    for i,waveRng in enumerate(args):
        xNum = (numpy.arange(0,nsamples+1.0)/nsamples)* \
            (numpy.nanmax(waveRng)-numpy.nanmin(waveRng))+numpy.nanmin(waveRng)
        yNum = f(xNum)
        yNum_e = s(xNum)

# now do MonteCarlo measurement of value and uncertainty
        for j in numpy.arange(0,nsamples):

# doing this for noise = nan
            if (numpy.isnan(yNum_e[0]) == False):
                yVar = yNum+numpy.random.normal(0.,1.)*yNum_e
            else:
                yVar = yNum
            
# choose function for measuring indices
            if (sample == 'integrate'):
                values[i,j] = trapz(yVar,xNum)
            elif (sample == 'average'):
                values[i,j] = numpy.nanmean(yVar)
            elif (sample == 'median'):
                values[i,j] = numpy.median(yVar)
            elif (sample == 'maximum'):
                values[i,j] = numpy.nanmax(yVar)
            elif (sample == 'minimum'):
                values[i,j] = numpy.nanmin(yVar)
            else:
                values[i,j] = numpy.nanmean(yVar)

# compute index based on defined method
# default is a simple ratio
    if (method == 'ratio'):
        vals = values[0,:]/values[1,:]
    elif (method == 'line'):
        vals = (values[0,:]+values[1,:])/values[2,:]
    elif (method == 'change'):
        vals = 2.*(values[0,:]-values[1,:])/(values[0,:]+values[1,:])
    elif (method == 'allers'):
        vals = (((numpy.mean(args[0])-numpy.mean(args[1]))/(numpy.mean(args[2])-numpy.mean(args[1])))*values[2,:] \
            + ((numpy.mean(args[2])-numpy.mean(args[0]))/(numpy.mean(args[2])-numpy.mean(args[1])))*values[1,:]) \
            /values[0,:]
    else:
        vals = values[0,:]/values[1,:]
            
# output mean, standard deviation
    if (noiseFlag):
        return numpy.nanmean(vals), numpy.nan
    else:
        return numpy.nanmean(vals), numpy.nanstd(vals)


# wrapper function for measuring specific sets of indices

def measureIndexSet(sp,**kwargs):

# keyword parameters
    set = kwargs.get('set','burgasser')

# determine combine method
    if (set.lower() == 'burgasser'):
        reference = 'Indices from Burgasser et al. (2006)'
        names = ['H2O-J','CH4-J','H2O-H','CH4-H','H2O-K','CH4-K','K-J']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.14,1.165],[1.26,1.285],method='ratio',sample='integrate',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[1.315,1.335],[1.26,1.285],method='ratio',sample='integrate',**kwargs)
        inds[2],errs[2] = measureIndex(sp,[1.48,1.52],[1.56,1.60],method='ratio',sample='integrate',**kwargs)
        inds[3],errs[3] = measureIndex(sp,[1.635,1.675],[1.56,1.60],method='ratio',sample='integrate',**kwargs)
        inds[4],errs[4] = measureIndex(sp,[1.975,1.995],[2.08,2.12],method='ratio',sample='integrate',**kwargs)
        inds[5],errs[5] = measureIndex(sp,[2.215,2.255],[2.08,2.12],method='ratio',sample='integrate',**kwargs)
        inds[6],errs[6] = measureIndex(sp,[2.06,2.10],[1.25,1.29],method='ratio',sample='integrate',**kwargs)
    elif (set.lower() == 'tokunaga'):
        reference = 'Indices from Tokunaga & Kobayashi (1999)'
        names = ['K1','K2']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[2.1,2.18],[1.96,2.04],method='change',sample='average',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[2.2,2.28],[2.1,2.18],method='change',sample='average',**kwargs)
    elif (set.lower() == 'reid'):
        reference = 'Indices from Reid et al. (2001)'
        names = ['H2O-A','H2O-B']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.33,1.35],[1.28,1.30],method='ratio',sample='average',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[1.47,1.49],[1.59,1.61],method='ratio',sample='average',**kwargs)
    elif (set.lower() == 'geballe'):
        reference = 'Indices from Geballe et al. (2002)'
        names = ['H2O-1.2','H2O-1.5','CH4-2.2']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.26,1.29],[1.13,1.16],method='ratio',sample='integrate',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[1.57,1.59],[1.46,1.48],method='ratio',sample='integrate',**kwargs)
        inds[2],errs[2] = measureIndex(sp,[2.08,2.12],[2.215,2.255],method='ratio',sample='integrate',**kwargs)
    elif (set.lower() == 'allers'):
        reference = 'Indices from Allers et al. (2007), Allers & Liu (2013)'
        names = ['H2O','FeH-z','VO-z','FeH-J','KI-J','H-cont']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.55,1.56],[1.492,1.502],method='ratio',sample='average',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[0.99135,1.00465],[0.97335,0.98665],[1.01535,1.02865],method='allers',sample='average',**kwargs)
        inds[2],errs[2] = measureIndex(sp,[1.05095,1.06505],[1.02795,1.04205],[1.07995,1.09405],method='allers',sample='average',**kwargs)
        inds[3],errs[3] = measureIndex(sp,[1.19880,1.20120],[1.19080,1.19320],[1.20680,1.20920],method='allers',sample='average',**kwargs)
        inds[4],errs[4] = measureIndex(sp,[1.23570,1.25230],[1.21170,1.22830],[1.26170,1.27830],method='allers',sample='average',**kwargs)
        inds[5],errs[5] = measureIndex(sp,[1.54960,1.57040],[1.45960,1.48040],[1.65960,1.68040],method='allers',sample='average',**kwargs)
    elif (set.lower() == 'slesnick'):
        reference = 'Indices from Slesnick et al. (2004)'
        names = ['H2O-1','H2O-2','FeH']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.335,1.345],[1.295,1.305],method='ratio',sample='average',**kwargs)
        inds[1],errs[1] = measureIndex(sp,[2.035,2.045],[2.145,2.155],method='ratio',sample='average',**kwargs)
        inds[2],errs[2] = measureIndex(sp,[1.1935,1.2065],[1.2235,1.2365],method='ratio',sample='average',**kwargs)
    elif (set.lower() == 'mclean'):
        reference = 'Indices from McLean et al. (2003)'
        names = ['H2OD']
        inds = numpy.zeros(len(names))
        errs = numpy.zeros(len(names))
        inds[0],errs[0] = measureIndex(sp,[1.951,1.977],[2.062,2.088],method='ratio',sample='average',**kwargs)
    else:
        print '{} is not one of the sets used for measureIndexSet'.format(set)
        return numpy.nan

# output dictionary of indices
    result = {names[i]: (inds[i],errs[i]) for i in numpy.arange(len(names))}
#    result['reference'] = reference
#    return inds,errs,names

    return result



# To do:
#     masking telluric regions
#    labeling features
#     add legend
def plotSpectrum(*args, **kwargs):

# error check - make sure you're plotting something
    if (len(args) < 1):
        print 'plotSpectrum needs at least on Spectrum object to plot'
        return
#    if isinstance(args[0],Spectrum):
#        print 'plotSpectrum needs at least one Spectrum object to plot'
#        return

# this loop solves issues if a list of spectrum objects is provided accidentally
    sp = []
    for i,a in enumerate(args):
        if (type(a) == list):
            sp.append(a[0])
        else:
            sp.append(a)

# absorption features
    feature_labels = { \
        'h2o': {'label': r'H$_2$O', 'type': 'band', 'wavelengths': [[0.92,0.95],[1.08,1.20],[1.325,1.450],[1.72,2.14]]}, \
        'ch4': {'label': r'CH$_4$', 'type': 'band', 'wavelengths': [[1.1,1.24],[1.28,1.44],[1.6,1.76],[2.05,2.35]]}, \
        'co': {'label': r'CO$$', 'type': 'band', 'wavelengths': [[2.28,2.42]]}, \
        'tio': {'label': r'TiO$$', 'type': 'band', 'wavelengths': [[0.76,0.80],[0.825,0.831]]}, \
        'vo': {'label': r'VO$$', 'type': 'band', 'wavelengths': [[1.04,1.08]]}, \
        'feh': {'label': r'FeH$$', 'type': 'band', 'wavelengths': [[0.86,0.90],[0.98,1.03],[1.19,1.31],[1.57,1.64]]}, \
        'h2': {'label': r'H$_2$', 'type': 'band', 'wavelengths': [[2.05,2.6]]}, \
        'oh': {'label': r'tell$$', 'type': 'band', 'wavelengths': [[1.37,1.45],[1.82,2.0]]}, \
        'sb': {'label': r'*$$', 'type': 'band', 'wavelengths': [[1.6,1.64]]}, \
        'h': {'label': r'H I$$', 'type': 'line', 'wavelengths': [[1.004,1.005],[1.093,1.094],[1.281,1.282],[1.944,1.945],[2.166,2.166]]},\
        'na': {'label': r'Na I$$', 'type': 'line', 'wavelengths': [[0.8186,0.8195],[1.136,1.137],[2.206,2.209]]}, \
        'k': {'label': r'K I$$', 'type': 'line', 'wavelengths': [[0.7699,0.7665],[1.169,1.177],[1.244,1.252]]}}


# keyword parameters
    nsamples = kwargs.get('nsamples',1000)
    title = kwargs.get('title','')
    zeropoint = kwargs.get('zeropoint',[0. for x in range(len(sp))])
    xlabel = kwargs.get('xlabel','{} ({})'.format(sp[0].wlabel,sp[0].wunit))
    ylabel = kwargs.get('ylabel','{} {} ({})'.format(sp[0].fscale,sp[0].flabel,sp[0].funit))
#    xrange = kwargs.get('xrange',[x.value for x in sp[0].waveRange()])
    xrange = kwargs.get('xrange',[0.85,2.4])
    bound = xrange
    ymax = [s.fluxMax().value for s in sp]
    yrange = kwargs.get('yrange',[0,1.2*(numpy.nanmax(ymax)+numpy.nanmax(zeropoint))])
    bound.extend(yrange)
    grid = kwargs.get('grid',False)
    colors = kwargs.get('colors',['k' for x in range(len(sp))])
    if (len(colors) < len(args)):
        colors.extend(['k' for x in range(len(sp)-len(colors))])
    colorsUnc = kwargs.get('colors',['k' for x in range(len(sp))])
    if (len(colorsUnc) < len(sp)):
        colorsUnc.extend(['k' for x in range(len(sp)-len(colorsUnc))])
    linestyle = kwargs.get('linestyle',['steps' for x in range(len(sp))])
    if (len(linestyle) < len(sp)):
        linestyle.extend(['steps' for x in range(len(sp)-len(linestyle))])
    filename = kwargs.get('filename','')
    format = kwargs.get('format',filename.split('.')[-1])
    showNoise = kwargs.get('showNoise',[False for x in range(len(sp))])
    if not isinstance(showNoise, list):
        showNoise = [showNoise]
    if (len(showNoise) < len(sp)):
        showNoise.extend([True for x in range(len(sp)-len(showNoise))])
    showZero = kwargs.get('showZero',[False for x in numpy.arange(len(sp))])
    if not isinstance(showZero, list):
        showZero = [showZero]
    if (len(showZero) < len(sp)):
        showZero.extend([True for x in range(len(sp)-len(showZero))])
    features = kwargs.get('features',[])
    if (kwargs.get('ldwarf',False) or kwargs.get('mdwarf',False)):
        features = list(set(features)|set(['H2O','TiO','CO','K','NA','FEH','H2']))
    if (kwargs.get('tdwarf',False)):
        features = list(set(features)|set(['H2O','CH4','K','H2']))
    if (kwargs.get('young',False)):
        features = list(set(features)|set(['VO']))
    if (kwargs.get('telluric',False)):
        features = list(set(features)|set(['OH']))
    if (kwargs.get('binary',False)):
        features = list(set(features)|set(['SB']))
#    mask = kwargs.get('mask',False)                # not yet implemented
#    labels = kwargs.get('labels','')            # not yet implemented


#    plt.clf()
# loop through sources
    plt.subplots(1)
    for ii,a in enumerate(sp):
        flx = [i+zeropoint[ii] for i in a.flux.value]
        plt.plot(a.wave.value,flx,color=colors[ii],linestyle=linestyle[ii])
# show noise
        if (showNoise[ii]):
            ns = [i+zeropoint[ii] for i in a.noise.value]
            plt.plot(a.wave.value,ns,color=colorsUnc[ii],linestyle=linestyle[ii],alpha=0.3)
# zeropoint
        if (showZero[ii]):
            ze = numpy.ones(len(a.flux))*zeropoint[ii]
            plt.plot(a.wave.value,ze,color=colors[ii],linestyle=':',alpha=0.3)
# determine maximum flux for all spectra
        f = interp1d(a.wave,flx,bounds_error=False,fill_value=0.)
        if (ii == 0):
            flxmax = flx
            wvmax = a.wave
        else:
            flxmax = numpy.maximum(flxmax,f(wvmax))
	         
# grid
    if (grid):
        plt.grid()

# label features
    f = interp1d(wvmax,flxmax,bounds_error=False,fill_value=0.)
    yoff = 0.02*numpy.nanmax(yrange)
    xset = [99.,99.]
    oflg = False
    for ftr in features:
        ftr = ftr.lower()
        if ftr in feature_labels:
            for ii,waveRng in enumerate(feature_labels[ftr]['wavelengths']):
                if (max(waveRng) > min(xrange)):
                    x = (numpy.arange(0,nsamples+1.0)/nsamples)* \
                        (numpy.nanmax(waveRng)-numpy.nanmin(waveRng)+0.1)+numpy.nanmin(waveRng)-0.05
                    y = numpy.nanmax(f(x))+0.5*yoff
#  THIS PART IS SUPPOSED TO SOLVE OVERLAP PROBLEM BUT NOT YET WORKING
                    if oflg:
#                        flg = [1 if ((numpy.nanmin(waveRng) < numpy.nanmin(w) and numpy.max(waveRng) > numpy.nanmax(w)) or (numpy.nanmin(waveRng) > numpy.nanmin(w) and numpy.nanmax(waveRng) < numpy.nanmax(w))) else 0 for w in xset]
#                        flg = [1 if ((waveRng[0] < w[0] and waveRng[1] > w[1]) or (waveRng[0] > w[0] and waveRng[1] < w[1])) else 0 for w in xset]
                        flg1 = [1 if (waveRng[0] < w[0] and waveRng[1] > w[1]) else 0 for w in xset]
                        flg2 = [1 if (min(waveRng) > min(w) and max(waveRng) < max(w)) else 0 for w in xset]
                        flg = flg1+flg2
#                        flg = [1 if (abs(numpy.mean(waveRng)-numpy.mean(w))<0.1) else 0 for w in xset]
                        y = y+4*yoff*numpy.sum(flg)
                        print ftr, numpy.sum(flg1), numpy.sum(flg2) #, [numpy.mean(a)-numpy.mean(waveRng) for a in xset]
                    else:
                        oflg = True
                    xset = [xset,waveRng]
#                w = numpy.where(numpy.nanmin(numpy.abs(numpy.subtract(xset,[numpy.mean(waveRng)]*len(xset)))) < 0.1)
#                if (len(w[0]) > 0):
#                    print ftr, waveRng, w, len(w[0]), xset[w[0]], numpy.abs(numpy.subtract(xset,[numpy.mean(waveRng)]*len(xset)))
#                    y = y+4*yoff*len(w)
#                if numpy.nanmin(numpy.abs(numpy.subtract(xset,[numpy.mean(waveRng)]*len(xset)))) < 0.2:
#                    y = y+4*yoff
#                xset.append(numpy.mean(waveRng))
                    if feature_labels[ftr]['type'] == 'band':
                        plt.plot(waveRng,[y+yoff]*2,color='k',linestyle='-')
                        plt.plot([waveRng[0]]*2,[y,y+yoff],color='k',linestyle='-')
                        plt.text(numpy.mean(waveRng),y+1.5*yoff,feature_labels[ftr]['label'],horizontalalignment='center')
                    else:
                        for w in waveRng:
                            plt.plot([w]*2,[y,y+yoff],color='k',linestyle='-')
                        plt.text(numpy.mean(waveRng),y+1.5*yoff,feature_labels[ftr]['label'],horizontalalignment='center')


# axis labels
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.axis(bound)
    plt.title(title)
    
# save to filen or display
    if (len(filename) > 0): 
        plt.savefig(filename, format=format)
    
    else:
        plt.show()
        if (kwargs.get('interactive',False) != False):
            plt.ion()        # make window interactive by default
        else:
            plt.ioff()
    return


def properCoordinates(c):
    '''converts various coordinate forms to the proper SkyCoord format'''
    if isinstance(c,SkyCoord):
        return c
    elif isinstance(c,list):
        return SkyCoord(c[0]*u.deg,c[1]*u.deg,frame='icrs')
# input is sexigessimal string
    elif isinstance(c,str):
        return SkyCoord(c,'icrs', unit=(u.hourangle, u.deg))
    else:
        raise ValueError('\nCould not parse input format\n\n')


def readSpectrum(**kwargs):

# TO BE DONE:
# FIX IF THERE IS NO NOISE CHANNEL
# PRODUCE AND RETURN HEADER => CHANGE OUTPUT TO DICTIONARY?
# NOTE: THIS IS STRICTLY A LOCAL READ PROGRAM
    
# keyword parameters
    folder = kwargs.get('folder','')
    catchSN = kwargs.get('catchSN',True)
    file = kwargs.get('filename','')
#    url = kwargs.get('url',SPLAT_URL)+'/Spectra/'
#    local = kwargs.get('local',False)
    
# download if a remote file
#    if url != '' and not local:
#        try:
#            open(os.path.basename(TMPFILENAME), 'wb').write(urllib2.urlopen(url+file).read()) 
#            file = os.path.basename(TMPFILENAME)
#            print 'Using {}'.format(TMPFILENAME)
#        except:
#            print '\n\nCould not locate {} at {}\n'.format(file,url)

# try to read        
    if (os.path.exists(file) == False):
        file = folder+os.path.basename(file)
    if (os.path.exists(file) == False):
        raise NameError('\nCould not find ' + file+'\n\n')
    
# determine which type of file
    ftype = file.split('.')[-1]

# fits file    
    if (ftype == 'fit' or ftype == 'fits'):
        data = fits.open(file)
        if 'NAXIS3' in data[0].header.keys():
            d = data[0].data[0,:,:]
        else:
            d = data[0].data
        header = data[0].header
        data.close()

# ascii file    
    else:
        try:
            d = numpy.genfromtxt(file, comments='#', unpack=False, \
                missing_values = ('NaN','nan'), filling_values = (numpy.nan)).transpose()
        except ValueError:
            d = numpy.genfromtxt(file, comments=';', unpack=False, \
                 missing_values = ('NaN','nan'), filling_values = (numpy.nan)).transpose()
        header = fits.Header()
        
# assign arrays to wave, flux, noise
    wave = d[0,:]
    flux = d[1,:]
    if len(d[:,0]) > 2:
        noise = d[2,:]
    else:
        noise = numpy.zeros(len(flux))
        noise[:] = numpy.nan        

# fix places where noise is claimed to be 0
    w = numpy.where(noise == 0.)
    noise[w] = numpy.nan

# fix nans in flux
    w = numpy.where(numpy.isnan(flux) == True)
    flux[w] = 0.

# fix to catch badly formatted files where noise column is S/N                 
#    print flux, numpy.median(flux)
    if (catchSN):
          w = numpy.where(flux > stats.nanmedian(flux))
          if (stats.nanmedian(flux[w]/noise[w]) < 1.):
              noise = flux/noise
              w = numpy.where(numpy.isnan(noise))
              noise[w] = stats.nanmedian(noise)

# clean up
#    if url != '' and not local:
#        os.remove(os.path.basename(TMPFILENAME))

    return {'wave':wave,'flux':flux,'noise':noise,'header':header}



def searchLibrary(*args, **kwargs):
    '''Search the SpeX database to extract the key reference for that Spectrum
        Note that this is currently only and AND search - need to figure out
        how to a full SQL style search'''
# program parameters
    ref = kwargs.get('output','all')
    radius = kwargs.get('radius',10.)      # search radius in arcseconds
    classes = ['young','subdwarf','binary','spbinary','red','blue','giant','wd','standard','companion']

# get database
    data = fetchDatabase(**kwargs)
    if (ref not in data.colnames and ref != 'all'):
        print '\nWarning: searchLibrary cannot return unknown column {}; returning filename instead\n\n'.format(ref)
        ref = 'all'
    data['select'] = numpy.zeros(len(data['ra']))
    count = 0.
    
# search by filename
    file = kwargs.get('file','')
    file = kwargs.get('filename',file)
    if (file != ''):
        if isinstance(file,str):
            file = [file]
        for f in file:
            data['select'][numpy.where(data['data_file'] == f)] += 1
        count+=1.
# exclude by filename
    if kwargs.get('excludefile',False) != False:
        file = kwargs['excludefile']
        if isinstance(file,str):
            file = [file]
        for f in file:
            data['select'][numpy.where(data['data_file'] != f)] += 1
        count+=1.
# search by name
    if kwargs.get('name',False) != False:
        nm = kwargs['name']
        if isinstance(nm,str):
            nm = [nm]
        for n in nm:
            data['select'][numpy.where(data['name'] == n)] += 1
        count+=1.
# search by shortname
    if kwargs.get('shortname',False) != False:
        sname = kwargs['shortname']
        if isinstance(sname,str):
            sname = [sname]
        for sn in sname:
            if sn[0].lower() != 'j':
                sn = 'J'+sn
            data['select'][numpy.where(data['shortname'] == sn)] += 1
        count+=1.
# exclude by shortname
    if kwargs.get('excludesource',False) != False:
        sname = kwargs['excludesource']
        if isinstance(sname,str):
            sname = [sname]
        for sn in sname:
            if sn[0].lower() != 'j':
                sn = 'J'+sn
            data['select'][numpy.where(data['shortname'] != sn)] += 1
        count+=1.
# search by reference list
    if kwargs.get('reference',False) != False:
        refer = kwargs['reference']
        if isinstance(ref,str):
            refer = [refer]
        for r in refer:
            data['select'][numpy.where(data['data_reference'] == r)] += 1
        count+=1.
# search by designation
    if kwargs.get('designation',False) != False:
        desig = kwargs['designation']
        if isinstance(desig,str):
            desig = [desig]
        for d in desig:
            data['select'][numpy.where(data['designation'] == d)] += 1
        count+=1.
# search by observation date range
    if kwargs.get('date',False) != False:
        date = kwargs['date']
        if isinstance(date,str) or isinstance(date,long) or isinstance(date,float) or isinstance(date,int):
            date = [float(date),float(date)]
        elif isinstance(date,list):
            date = [float(date[0]),float(date[-1])]
        else:
            raise ValueError('\nCould not parse date input {}\n\n'.format(date))
        data['daten'] = [float(x) for x in data['observation_date']]
        data['select'][numpy.where(numpy.logical_and(data['daten'] >= date[0],data['daten'] <= date[1]))] += 1
        count+=1.
# search by coordinate - NOTE: THIS IS VERY SLOW RIGHT NOW
    if kwargs.get('coordinate',False) != False:
        coord = kwargs['coordinate']
        if isinstance(coord,SkyCoord):
            cc = coord
        else:
            cc = properCoordinates(coord)
        data['separation'] = [cc.separation(data['skycoords'][i]).arcsecond for i in numpy.arange(len(data['skycoords']))]
        data['select'][numpy.where(data['separation'] <= radius)] += 1
        count+=1.
# search by spectral type
    sref = ''
    if (kwargs.get('spt',False) != False):
        sref = 'lit_type'
        spt = kwargs['spt']
    if (kwargs.get('spex_spt',False) != False):
        sref = 'spex_type'
        spt = kwargs['spex_spt']
    if (kwargs.get('spex_type',False) != False):
        sref = 'spex_type'
        spt = kwargs['spex_type']
    if (kwargs.get('opt_spt',False) != False):
        sref = 'opt_type'
        spt = kwargs['opt_spt']
    if (kwargs.get('opt_type',False) != False):
        sref = 'opt_type'
        spt = kwargs['opt_type']
    if (kwargs.get('nir_spt',False) != False):
        sref = 'nir_type'
        spt = kwargs['nir_spt']
    if (kwargs.get('nir_type',False) != False):
        sref = 'nir_type'
        spt = kwargs['nir_type']
    if sref != '':
        if not isinstance(spt,list):        # one value = only this type
            spt = [spt,spt]
        if isinstance(spt[0],str):          # convert to numerical spt
            spt = [typeToNum(spt[0]),typeToNum(spt[1])]
        data['sptn'] = [typeToNum(x) for x in data[sref]]
        data['select'][numpy.where(numpy.logical_and(data['sptn'] >= spt[0],data['sptn'] <= spt[1]))] += 1
        count+=1.

# search by magnitude range
    if kwargs.get('jmag',False) != False:
        mag = kwargs['jmag']
        if not isinstance(mag,list):        # one value = faint limit
            mag = [0,mag]
        data['magn'] = [float(x) for x in data['jmag']]
        data['select'][numpy.where(numpy.logical_and(data['magn'] >= mag[0],data['magn'] <= mag[1]))] += 1
        count+=1.
    if kwargs.get('hmag',False) != False:
        mag = kwargs['hmag']
        if not isinstance(mag,list):        # one value = faint limit
            mag = [0,mag]
        data['magn'] = [float(x) for x in data['hmag']]
        data['select'][numpy.where(numpy.logical_and(data['magn'] >= mag[0],data['magn'] <= mag[1]))] += 1
        count+=1.
    if kwargs.get('kmag',False) != False:
        mag = kwargs['kmag']
        if not isinstance(mag,list):        # one value = faint limit
            mag = [0,mag]
        data['magn'] = [float(x) for x in data['kmag']]
        data['select'][numpy.where(numpy.logical_and(data['magn'] >= mag[0],data['magn'] <= mag[1]))] += 1
        count+=1.
# search by S/N range
    if kwargs.get('snr',False) != False:
        snr = kwargs['snr']
        if not isinstance(snr,list):        # one value = minimum S/N
            snr = [float(snr),1.e9]
        data['snrn'] = [float(x) for x in data['median_snr']]
        data['select'][numpy.where(numpy.logical_and(data['snrn'] >= snr[0],data['snrn'] <= snr[1]))] += 1
        count+=1.
# search by class
    for c in classes:
        if kwargs.get(c,'n') != 'n':
            test = kwargs.get(c)
            if isinstance(test,bool):
                data['select'][numpy.where(data[c] == test)]+=1
                count+=1.

# limit access to public data for most users
    if checkAccess() == False:
        data['select'][numpy.where(data['public'] != 'Y')] = 0

# logic of search
    logic = 'and'         # default combination
    logic = kwargs.get('combine',logic).lower()
    logic = kwargs.get('logic',logic).lower()
    if (logic == 'and'):
        data['select'] = numpy.floor(data['select']/count)
    elif (logic == 'or'):
        data['select'] = numpy.ceil(data['select']/count)
    else:
        raise NameError('\nDo not recognize logical operation {}; use logic = and/or\n\n'.format(logic))

# return sorted by ra by default
    if kwargs.get('sort',True) != False:
        data.sort('ra')
    if (ref == 'all'):
        return data[:][numpy.where(data['select']==1)]
    else:
        return data[ref][numpy.where(data['select']==1)]


def test():
    test_src = 'J1507-1627'

    sys.stderr.write('\n\n>>>>>>>>>>>> TESTING SPLAT CODE <<<<<<<<<<<<\n')
# check you are online
    if checkOnline():
        sys.stderr.write('\n...you are online and can see SPLAT website\n')
    else:
        sys.stderr.write('\n...you are NOT online or cannot see SPLAT website\n')

# check your access
    if checkAccess():
        sys.stderr.write('\n...you currently HAVE access to unpublished spectra\n')
    else:
        sys.stderr.write('\n...you currently DO NOT HAVE access to unpublished spectra\n')
        
# check you can search for and load a spectrum
    sp = getSpectrum(shortname=test_src)[0]
    sp.info()
    sys.stderr.write('\n...getSpectrum and loadSpectrum successful\n')

# check searchLibrary
    list = searchLibrary(young=True,output='data_file')
    sys.stderr.write('\n{} young spectra in the SPL  ...searchLibrary successful\n'.format(len(list)))

# check index measurement
    ind = measureIndexSet(sp,set='burgasser')
    sys.stderr.write('\nSpectral indices for '+test_src+':\n')
    for k in ind.keys():
        print '\t{:s}: {:4.3f}+/-{:4.3f}'.format(k, ind[k][0], ind[k][1])
    sys.stderr.write('...index measurement successful\n')

# check classification
    spt, spt_e = classifyByIndex(sp,set='burgasser')
    sys.stderr.write('\n...index classification of '+test_src+' = {:s}+/-{:2.1f}; successful\n'.format(spt,spt_e))

    spt, spt_e = classifyByStandard(sp,method='kirkpatrick')
    sys.stderr.write('\n...standard classification of '+test_src+' = {:s}+/-{:2.1f}; successful\n'.format(spt,spt_e))

    grav = classifyGravity(sp)
    sys.stderr.write('\n...gravity class of '+test_src+' = {:s}; successful\n'.format(grav))

# check SpT -> Teff
    teff, teff_e = typeToTeff(spt,unc=spt_e)
    sys.stderr.write('\n...Teff of '+test_src+' = {:.1f}+/-{:.1f} K; successful\n'.format(teff,teff_e))

# check flux calibration
    sp.normalize()
    sp.fluxCalibrate('2MASS J',15.0,apparent=True)
    mag,mag_e = filterMag(sp,'MKO J')
    sys.stderr.write('\n...apparent magnitude MKO J = {:3.2f}+/-{:3.2f} from 2MASS J = 15.0; filter calibration successful\n'.format(mag,mag_e))

# check models
    mdl = loadModel(teff=teff,logg=5.3,set='BTSettl2008')
    sys.stderr.write('\n...interpolated model generation successful\n')

# check normalization
    sys.stderr.write('\n...normalization successful\n')

# check compareSpectrum
    chi, scale = compareSpectra(sp,mdl,mask_standard=True,stat='chisqr')
    sys.stderr.write('\nFit to model: chi^2 = {}, scale = {}'.format(chi,scale))
    sys.stderr.write('\n...compareSpectra successful\n'.format(chi,scale))

# check plotSpectrum
    mdl.scale(scale)
    plotSpectrum(sp,mdl,colors=['k','r'],title='If this appears everything is OK: close window')
    sys.stderr.write('\n...plotSpectrum successful\n')
    sys.stderr.write('\n>>>>>>>>>>>> SPLAT TEST SUCCESSFUL; HAVE FUN! <<<<<<<<<<<<\n\n')


def typeToMag(spt, filt, **kwargs):
    """
    Takes a spectral type, its uncertainty, and a filter, returns absolute magnitude
    Filter options = ['MKO K', 'MKO H', 'MKO J', 'MKO Y', 'MKO LP', '2MASS J', '2MASS K', '2MASS H']
    References = ['faherty', 'dupuy', 'burgasser']
    """

#Keywords
    nsamples = kwargs.get('nsamples', 100)
    ref = kwargs.get('ref', 'dupuy')
    unc = kwargs.get('unc', 0.)

#Convert spectral type string to number
  
    if (type(spt) == str):
        spt = typeToNum(spt, uncertainty=unc)
    else:
        spt = copy.deepcopy(spt)

#Faherty
    if (ref.lower() == 'faherty'):
        sptoffset = 10.
        reference = 'Abs Mag/SpT relation from Faherty et al. (2012)'
        coeffs = { \
            'MKO J': {'fitunc' : 0.30, 'range' : [20., 38.],  \
                'coeff': [.000203252, -.0129143, .275734, -1.99967, 14.8948]}, \
            'MKO H': {'fitunc' : 0.27, 'range' : [20., 38.], \
                'coeff' : [.000175368, -.0108205, .227363, -1.60036, 13.2372]}, \
            'MKO K': {'fitunc' : 0.28, 'range' : [20., 38.], \
                'coeff' : [.0000816516, -.00469032, .0940816, -.485519, 9.76100]}}

# Burgasser
    elif (ref.lower() == 'burgasser'):
        sptoffset = 20.
        reference = 'Abs Mag/SpT relation from Burgasser (2007)'
        coeffs = { \
            'MKO K': {'fitunc' : 0.26, 'range' : [20., 38.], \
                'coeff': [.0000001051, -.000006985, .0001807, -.002271, .01414, -.04024, .05129, .2322, 10.45]}}
 
# Dupuy & Liu, default reference  
    elif (ref.lower() == 'dupuy'):
        reference = 'Abs Mag/SpT relation from Dupuy & Liu (2012)'
        sptoffset = 10.
        coeffs = { \
            'MKO J': {'fitunc' : 0.39, 'range' : [16., 39.], \
                'coeff' : [-.00000194920, .000227641, -.0103332, .232771, -2.74405, 16.3986, -28.3129]}, \
            'MKO Y': {'fitunc': 0.40, 'range' : [16., 39.], \
                'coeff': [-.00000252638, .000285027, -.0126151, .279438, -3.26895, 19.5444, -35.1560]}, \
            'MKO H': {'fitunc': 0.38, 'range' : [16., 39.], \
                'coeff': [-.00000224083, .000251601, -.0110960, .245209, -2.85705, 16.9138, -29.7306]}, \
            'MKO K': {'fitunc': 0.40, 'range' : [16., 39.], \
                'coeff': [-.00000104935, .000125731, -.00584342, .135177, -1.63930, 10.1248, -15.2200]}, \
            'MKO LP': {'fitunc': 0.28, 'range': [16., 39.], \
                'coeff': [0.00000, 0.00000, .0000546366, -.00293191, .0530581,  -.196584, 8.89928]}, \
            '2MASS J': {'fitunc': 0.40, 'range': [16., 39.], \
                'coeff': [-.000000784614, .000100820, -.00482973, .111715, -1.33053, 8.16362, -9.67994]}, \
            '2MASS H': {'fitunc': 0.40, 'range': [16., 38.5], \
                'coeff': [-.00000111499, .000129363, -.00580847, .129202, -1.50370, 9.00279, -11.7526]}, \
            '2MASS K': {'fitunc': 0.43, 'range':[16., 38.5], \
                'coeff': [0.00000, 0.00000, .000106693, -.00642118, .134163, -.867471, 11.0114]}}

    else:
        sys.stderr.write('\nInvalid Abs Mag/SpT relation given: %s\n' % ref)
        return numpy.nan, numpy.nan

    if (filt.upper() in coeffs.keys()) == 1:
        for filter in coeffs.keys():
            if filt.upper() == filter:
                coeff = coeffs[filter]['coeff']
                fitunc = coeffs[filter]['fitunc']
                range = coeffs[filter]['range']
    else:
        sys.stderr.write('\n Invalid filter given for %s\n' % reference)
        return numpy.nan, numpy.nan

# compute magnitude if its in the right spectral type range
    if (range[0] <= spt <= range[1]):
        if (unc > 0.):
            vals = numpy.polyval(coeff, numpy.random.normal(spt - sptoffset, unc, nsamples))
            abs_mag = numpy.nanmean(vals)
            abs_mag_error = (numpy.nanstd(vals)**2+fitunc**2)**0.5
            return abs_mag, abs_mag_error
        else:
            abs_mag = numpy.polyval(coeff, spt-sptoffset)
            return abs_mag, fitunc
    else:
        sys.stderr.write('\nSpectral Type is out of range for %s Abs Mag/SpT relation\n' % reference)
        return numpy.nan, numpy.nan


def typeToNum(input, **kwargs):
    '''convert between string and numeric spectral types'''
# keywords     
    error = kwargs.get('error','')
    unc = kwargs.get('uncertainty',0.)
    subclass = kwargs.get('subclass','')
    lumclass = kwargs.get('lumclass','')
    ageclass = kwargs.get('ageclass','')
    colorclass = kwargs.get('colorclass','')
    peculiar = kwargs.get('peculiar',False)
    spletter = 'KMLTY'

# number -> spectral type
    if (isNumber(input)):
        spind = int(abs(input/10))
        spdec = numpy.around(input,1)-spind*10.
        pstr = ''
        if (unc > 1.):
            error = ':'
        if (unc > 2.):
            error = '::'
        if (peculiar):
            pstr = 'p'
        if (0 <= spind < len(spletter)):
            output = colorclass+subclass+spletter[spind]+'{:3.1f}'.format(spdec)+ageclass+lumclass+pstr+error
        else:
            print 'Spectral type number must be between 0 ({}0) and {} ({}9)'.format(spletter[0],len(spletter)*10.-1.,spletter[-1])
            output = numpy.nan

# spectral type -> number
    elif isinstance(input,str):
        input = string.split(input,sep='+')[0]    # remove +/- sides
        input = string.split(input,sep='-')[0]    # remove +/- sides
        sptype = re.findall('[{}]'.format(spletter),input)
        if (len(sptype) == 1):
            output = spletter.find(sptype[0])*10.
            spind = input.find(sptype[0])+1
            if (spind < len(input)):
                if (input.find('.') < 0):
                    if (isNumber(input[spind])):
                        output = output+float(input[spind])
                else:
                    output = output+float(input[spind:spind+3])
                    spind = spind+3
            ytype = re.findall('[abcd]',input.split('p')[-1])
            if (len(ytype) == 1):
                ageclass = ytype[0]
            if (input.find('p') != -1):
                 peculiar = True
            if (input.find('sd') != -1):
                 subclass = 'sd'
            if (input.find('esd') != -1):
                 subclass = 'esd'
            if (input.find('usd') != -1):
                 subclass = 'usd'
            if (input.count('I') > 0):
                 lumclass = ''.join(re.findall('I',input))
            if (input.count(':') > 0):
                 error = ''.join(re.findall(':',input))
            if (input[0] == 'b' or input[0] == 'r'):
                 colorclass = input[0]
        if (len(sptype) != 1):
#            print 'Only spectral classes {} are handled with this routine'.format(spletter)
            output = numpy.nan
# none of the above - return the input
    else:
        output = input
    return output


def typeToTeff(input, **kwargs):
    '''return Teff for a given SpT'''
# keywords     
    nsamples = kwargs.get('nsamples',100)
    unc = kwargs.get('uncertainty',0.001)
    unc = kwargs.get('unc',unc)
    unc = kwargs.get('spt_e',unc)
    ref = kwargs.get('ref','stephens2009')
    ref = kwargs.get('set',ref)
    ref = kwargs.get('method',ref)

# convert spectral type string to number
    if (type(input) == str):
        spt = typeToNum(input,uncertainty=unc)
    else:
        spt = copy.deepcopy(input)
    
    if spt < 20. and 'marocco' not in ref.lower():
        ref='stephens2009'

# choose among possible options

# Golimowski et al. (2004, AJ, 127, 3516)
    if ('golimowski' in ref.lower()):
        reference = 'Teff/SpT relation from Golimowski et al. (2004)'
        sptoffset = 10.
        coeff = [9.5373e-4,-9.8598e-2,4.0323,-8.3099e1,9.0951e2,-5.1287e3,1.4322e4]
        range = [16.,38.]
        fitunc = 124.

# Looper et al. (2008, ApJ, 685, 1183)
    elif ('looper' in ref.lower()):
        reference = 'Teff/SpT relation from Looper et al. (2008)'
        sptoffset = 20.
        coeff = [9.084e-4,-4.255e-2,6.414e-1,-3.101,1.950,-108.094,2319.92]
        range = [20.,38.]
        fitunc = 87.

# Stephens et al. (2009, ApJ, 702, 1545); using OPT/IR relation for M6-T8
# plus alternate coefficients for L3-T8
    elif ('stephens' in ref.lower()):
        reference = 'Teff/SpT relation from Stephens et al. (2009)'
        sptoffset = 10.
        coeff = [-0.0025492,0.17667,-4.4727,54.67,-467.26,4400.]
        range = [16.,38.]
        fitunc = 100.
        coeff_alt = [-0.011997,1.2315,-50.472,1031.9,-10560.,44898.]
        range_alt = [23.,38.]

# Marocco et al. (2013, AJ, 146, 161)
    elif ('marocco' in ref.lower()):
        reference = 'Teff/SpT relation from Marocco et al. (2013)'
        sptoffset = 10.
        coeff = [7.4211e-5,-8.43736e-3,3.90319e-1,-9.46896,129.141,-975.953,3561.47,-1613.82]
        range = [17.,38.]
        fitunc = 140.

    else:
        sys.stderr.write('\nInvalid Teff/SpT relation given ({})\n'.format(ref))
        return numpy.nan, numpy.nan

    if (range[0] <= spt <= range[1]):
        vals = numpy.polyval(coeff,numpy.random.normal(spt-sptoffset,unc,nsamples))
        if ('stephens' in ref.lower()):
            if (range_alt[0] <= spt <= range_alt[1]):
                vals = numpy.polyval(coeff_alt,numpy.random.normal(spt-sptoffset,unc,nsamples))
        teff = numpy.nanmean(vals)
        teff_e = (numpy.nanstd(vals)**2+fitunc**2)**0.5
        return teff, teff_e
    else:
        sys.stderr.write('\nSpectral Type is out of range for {:s} Teff/SpT relation\n'.format(reference))
        return numpy.nan, numpy.nan


def weightedMeanVar(vals, winp, *args, **kwargs):
    '''Compute weighted mean of an array of values through various methods'''
    
    method = kwargs.get('method','')
    minwt = kwargs.get('weight_minimum',0.)
    dof = kwargs.get('dof',len(vals)-1)
    if (numpy.nansum(winp) <= 0.):
        weights = numpy.ones(len(vals))
    if isinstance(winp,astropy.units.quantity.Quantity):
        winput = winp.value
    else:
        winput = copy.deepcopy(winp)

# uncertainty weighting: input is unceratinties   
    if (method == 'uncertainty'):
        weights = [w**(-2) for w in winput]
# ftest weighting: input is chisq values, extra dof value is required   
    elif (method == 'ftest'):
# fix issue of chi^2 = 0
        minchi = numpy.nanmin(winput)
        weights = numpy.array([stats.f.pdf(w/minchi,dof,dof) for w in winput])
# just use the input as the weights
    else:
        weights = [w for w in winput]
    
    weights = weights/numpy.nanmax(weights)
    weights[numpy.where(weights < minwt)] = 0.
    mn = numpy.nansum(vals*weights)/numpy.nansum(weights)
    var = numpy.nansum(weights*(vals-mn)**2)/numpy.nansum(weights)
    
    return mn,var        

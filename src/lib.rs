//! Python bindings for the P.56 active speech level meter (PyO3).
//!
//! Compiled into the `p56_asl._native` extension module by maturin. The
//! algorithm itself lives in the pure-Rust modules (`actlevel`, `filter`,
//! `histogram`, ...) and is unit-tested without Python.

mod actlevel;
mod constants;
mod error;
mod filter;
mod histogram;
mod params;
mod prefilter;
mod resample;

use numpy::{PyArray1, PyArrayDescrMethods, PyArrayMethods, PyUntypedArray, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Converts a numpy 1-D array of any supported dtype to `Vec<f32>`,
/// dividing integer samples by their maximum representable value
/// Converts a numpy 1-D array of float32/float64 samples to `Vec<f32>`.
///
/// The meter always works internally in f32 (like the reference
/// implementation); integer WAV files are converted to floats at the
/// boundary by the reader (soundfile) before reaching the core.
fn samples_to_f32(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<f32>> {
    let arr: &Bound<'_, PyUntypedArray> = obj
        .downcast()
        .map_err(|_| PyValueError::new_err("samples must be a numpy array, not a list"))?;
    if arr.ndim() != 1 {
        return Err(PyValueError::new_err(format!(
            "samples must be 1-D, got {} dimensions",
            arr.ndim()
        )));
    }
    let dtype = arr.dtype();
    macro_rules! convert {
        ($ty:ty) => {{
            let a = obj
                .clone()
                .downcast_into::<PyArray1<$ty>>()
                .expect("dtype checked above");
            unsafe { a.as_slice()? }.iter().map(|v| *v as f32).collect()
        }};
    }
    if dtype.is_equiv_to(&numpy::dtype::<f32>(py)) {
        Ok(convert!(f32))
    } else if dtype.is_equiv_to(&numpy::dtype::<f64>(py)) {
        Ok(convert!(f64))
    } else {
        Err(PyValueError::new_err(
            "unsupported dtype: expected float32 or float64",
        ))
    }
}

/// Extended ITU-T Rec. P.56 active speech level meter (Rust core).
#[pyclass(module = "p56_asl._native", name = "ActiveSpeechLevelMeter")]
struct PyActiveSpeechLevelMeter {
    inner: actlevel::ActiveSpeechLevelMeter,
    /// Resampler for input rates below 16 kHz; `None` when the input is
    /// already at least 16 kHz.
    resampler: Option<resample::Resampler>,
    /// Total input samples fed (pre-resampling), for `flush` length math.
    total_input: u64,
}

#[pymethods]
impl PyActiveSpeechLevelMeter {
    #[new]
    #[pyo3(signature = (sample_rate=8000.0, bit_depth=24, block_size=256, max_amplitude=1.0, auto_calibrate=false))]
    fn new(
        sample_rate: f64,
        bit_depth: u32,
        block_size: usize,
        max_amplitude: f64,
        auto_calibrate: bool,
    ) -> PyResult<Self> {
        // When the input rate is below 16 kHz the signal is resampled to
        // the 16 kHz operating rate, so the envelope filter and hangover
        // must be timed for 16 kHz — not the (lower) input rate.
        let effective_rate = if sample_rate < resample::TARGET_RATE as f64 {
            resample::TARGET_RATE as f64
        } else {
            sample_rate
        };
        let params = params::Params {
            sample_rate: effective_rate,
            bit_depth,
            block_size,
            max_amplitude,
            auto_calibrate,
        };
        let inner = actlevel::ActiveSpeechLevelMeter::new(params)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let resampler = if sample_rate < resample::TARGET_RATE as f64 {
            Some(
                resample::Resampler::new(sample_rate as u32, resample::TARGET_RATE)
                    .map_err(|e| PyValueError::new_err(e.to_string()))?,
            )
        } else {
            None
        };
        Ok(Self {
            inner,
            resampler,
            total_input: 0,
        })
    }

    /// Processes one block of samples given as a 1-D numpy array with
    /// dtype float32, float64, int8, int16 or int32 (int32 also covers
    /// 24-bit data stored in the low 24 bits — pass `bit_depth=24`).
    /// Integer samples are normalized by their maximum representable
    /// value. Input rates below 16 kHz are resampled to 16 kHz
    /// automatically.
    fn process_block(&mut self, py: Python<'_>, samples: &Bound<'_, PyAny>) -> PyResult<()> {
        let samples_f32 = samples_to_f32(py, samples)?;
        self.total_input += samples_f32.len() as u64;
        let sixteen_k_samples: Vec<f32> = match &mut self.resampler {
            None => samples_f32,
            Some(resampler) => {
                let out = resampler
                    .process(&samples_f32)
                    .map_err(|e| PyValueError::new_err(e.to_string()))?;
                if out.is_empty() {
                    return Ok(());
                }
                out
            }
        };
        let mut result = Ok(());
        // Feed the meter in block_size chunks; the meter rejects longer blocks.
        let block = self.inner.params().block_size;
        for chunk in sixteen_k_samples.chunks(block) {
            if let Err(e) = self.inner.process_block(chunk) {
                result = Err(PyValueError::new_err(e.to_string()));
                break;
            }
        }
        result
    }

    /// Finalizes the measurement: flushes the resampler (zero-padding the
    /// final partial chunk) and processes any remaining 16 kHz samples.
    fn finish(&mut self) -> PyResult<PyMeasurement> {
        if let Some(resampler) = &mut self.resampler {
            let out = resampler
                .flush(self.total_input)
                .map_err(|e| PyValueError::new_err(e.to_string()))?;
            let block = self.inner.params().block_size;
            for chunk in out.chunks(block) {
                self.inner
                    .process_block(chunk)
                    .map_err(|e| PyValueError::new_err(e.to_string()))?;
            }
        }
        let m = self
            .inner
            .finish()
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(PyMeasurement { inner: m })
    }

    /// Resets all accumulated state; configuration is kept.
    fn reset(&mut self) {
        self.inner.reset();
        self.total_input = 0;
        if let Some(resampler) = &mut self.resampler {
            resampler.reset();
        }
    }

    #[getter]
    fn sample_rate(&self) -> f64 {
        self.inner.params().sample_rate
    }

    #[getter]
    fn bit_depth(&self) -> u32 {
        self.inner.params().bit_depth
    }

    #[getter]
    fn block_size(&self) -> usize {
        self.inner.params().block_size
    }

    #[getter]
    fn max_amplitude(&self) -> f64 {
        self.inner.max_amplitude()
    }

    #[getter]
    fn auto_calibrate(&self) -> bool {
        self.inner.params().auto_calibrate
    }
}

/// Result of a completed measurement.
#[pyclass(module = "p56_asl._native", name = "Measurement", frozen)]
#[derive(Clone)]
struct PyMeasurement {
    inner: actlevel::Measurement,
}

#[pymethods]
impl PyMeasurement {
    /// Active speech level, in dB re. `max_amplitude` (dBov by default).
    #[getter]
    fn active_speech_level_db(&self) -> f64 {
        self.inner.active_speech_level_db
    }

    /// Activity factor, in `0..1`.
    #[getter]
    fn activity_factor(&self) -> f64 {
        self.inner.activity_factor
    }

    /// Long-term RMS level, in dB re. `max_amplitude`.
    #[getter]
    fn rms_db(&self) -> f64 {
        self.inner.rms_db
    }

    /// Average (DC) level of the input samples.
    #[getter]
    fn dc_level(&self) -> f64 {
        self.inner.dc_level
    }

    /// Maximum positive sample.
    #[getter]
    fn peak_positive(&self) -> f64 {
        self.inner.peak_positive
    }

    /// Maximum negative sample (<= 0).
    #[getter]
    fn peak_negative(&self) -> f64 {
        self.inner.peak_negative
    }

    /// Maximum absolute sample.
    #[getter]
    fn peak_abs(&self) -> f64 {
        self.inner.peak_abs
    }

    /// Number of processed samples.
    #[getter]
    fn sample_count(&self) -> u64 {
        self.inner.sample_count
    }

    fn __repr__(&self) -> String {
        format!(
            "Measurement(active_speech_level_db={:.4}, activity_factor={:.4}, \
             rms_db={:.4}, sample_count={})",
            self.inner.active_speech_level_db,
            self.inner.activity_factor,
            self.inner.rms_db,
            self.inner.sample_count
        )
    }
}

/// P.56 protection pre-filter (clause 10.2/Table 3, Annex B/C).
///
/// Streaming-safe biquad cascade matching the tolerance corridor of the
/// selected band (NB, SWB or FB) at the configured sampling rate.
#[pyclass(module = "p56_asl._native", name = "PreFilter")]
struct PyPreFilter {
    inner: prefilter::PreFilter,
}

#[pymethods]
impl PyPreFilter {
    #[new]
    #[pyo3(signature = (band, fs))]
    fn new(band: &str, fs: f64) -> PyResult<Self> {
        let band =
            prefilter::Band::parse(band).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let inner = prefilter::PreFilter::new(band, fs)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self { inner })
    }

    /// Filters samples in place. Accepts a 1-D numpy array (float32 or
    /// float64) and returns a new float32 array.
    fn process(
        &mut self,
        py: Python<'_>,
        samples: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyArray1<f32>>> {
        let input = samples_to_f32(py, samples)?;
        let mut buf = input;
        self.inner.process(&mut buf);
        let out = PyArray1::<f32>::from_vec(py, buf);
        Ok(out.unbind())
    }

    /// Resets the filter state.
    fn reset(&mut self) {
        self.inner.reset();
    }

    /// Magnitude response `|H(f)|` at frequency `f` (Hz), relative to 1 kHz.
    #[pyo3(name = "response_db")]
    fn response_db(&self, f: f64) -> f64 {
        self.inner.response_db(f)
    }

    /// Band name ("nb", "swb" or "fb").
    #[getter]
    fn band(&self) -> &'static str {
        self.inner.band().as_str()
    }

    /// Sampling rate in Hz.
    #[getter]
    fn sample_rate(&self) -> f64 {
        self.inner.fs()
    }

    /// Number of biquad sections.
    #[getter]
    fn num_sections(&self) -> usize {
        self.inner.num_sections()
    }
}

/// Stateful FFT resampler from any input rate to any target rate, mono.
///
/// Used by the CLI for `--fs`: streaming-safe — the rubato instance
/// carries its overlap across `process` calls. `flush` zero-pads the
/// final partial chunk and trims the ramp-up delay so the total output
/// length equals `round(total_input * target / source)`.
#[pyclass(module = "p56_asl._native", name = "Resampler")]
struct PyResampler {
    inner: resample::Resampler,
    total_input: u64,
}

#[pymethods]
impl PyResampler {
    /// Creates a resampler from `sample_rate` to `target_rate` (Hz).
    ///
    /// # Errors
    ///
    /// [`pyo3::exceptions::PyValueError`] for invalid rates or internal
    /// construction failures.
    #[new]
    #[pyo3(signature = (sample_rate, target_rate))]
    fn new(sample_rate: u32, target_rate: u32) -> PyResult<Self> {
        let inner = resample::Resampler::new(sample_rate, target_rate)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(Self {
            inner,
            total_input: 0,
        })
    }

    /// Feeds samples (float32/float64 numpy array); returns all output
    /// available so far.
    fn process(&mut self, py: Python<'_>, samples: &Bound<'_, PyAny>) -> PyResult<Vec<f32>> {
        let samples = samples_to_f32(py, samples)?;
        self.total_input += samples.len() as u64;
        self.inner
            .process(&samples)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Zero-pads and drains; returns the final output samples.
    fn flush(&mut self) -> PyResult<Vec<f32>> {
        let total = self.total_input;
        self.inner
            .flush(total)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Source rate in Hz.
    #[getter]
    fn sample_rate(&self) -> u32 {
        self.inner.source_rate()
    }

    /// Target rate in Hz.
    #[getter]
    fn target_rate(&self) -> u32 {
        self.inner.target_rate()
    }
}

/// The `p56_asl._native` extension module.
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyActiveSpeechLevelMeter>()?;
    m.add_class::<PyMeasurement>()?;
    m.add_class::<PyPreFilter>()?;
    m.add_class::<PyResampler>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}

// Re-export the pure-Rust API for `cargo test` and future Rust consumers.
pub use actlevel::{bin_interp, ActiveSpeechLevelMeter, Measurement};
pub use error::{Error, Result};
pub use params::Params;
pub use prefilter::{Band, PreFilter};
pub use resample::Resampler;

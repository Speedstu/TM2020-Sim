//! Checked bindings to tm2020_policy.dll. No game hooks or injection are implied.
//! The C++ module must outlive its opaque policy handle; this type owns both.
#![cfg(windows)]
use std::ffi::{c_char, c_void, CStr, CString, OsStr};
use std::marker::PhantomData;
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
use std::ptr::{self, NonNull};
use std::rc::Rc;

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryExW(name: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const c_char) -> *mut c_void;
    fn FreeLibrary(module: *mut c_void) -> i32;
}
#[repr(C)]
#[derive(Default)]
struct Info {
    size_bytes: u32,
    api_version: u32,
    observations: u32,
    actions: u32,
    width: u32,
    reserved: u32,
}
type Open = unsafe extern "C" fn(*const c_char, *mut *mut c_void) -> i32;
type Close = unsafe extern "C" fn(*mut c_void);
type GetInfo = unsafe extern "C" fn(*mut c_void, *mut Info) -> i32;
type Predict = unsafe extern "C" fn(*mut c_void, *const f64, u32, *mut f64, u32, *mut f64) -> i32;
type Schema = unsafe extern "C" fn(*mut c_void) -> *const c_char;
type LastError = unsafe extern "C" fn() -> *const c_char;
type Version = unsafe extern "C" fn() -> u32;
struct Library(NonNull<c_void>);
impl Drop for Library {
    fn drop(&mut self) {
        unsafe {
            FreeLibrary(self.0.as_ptr());
        }
    }
}
impl Library {
    fn symbol(&self, name: &CStr) -> Result<*mut c_void, String> {
        let p = unsafe { GetProcAddress(self.0.as_ptr(), name.as_ptr()) };
        if p.is_null() {
            Err(format!("Missing DLL export: {}", name.to_string_lossy()))
        } else {
            Ok(p)
        }
    }
}
pub struct Policy {
    handle: NonNull<c_void>,
    close: Close,
    predict: Predict,
    last_error: LastError,
    observations: usize,
    actions: usize,
    schema: String,
    _library: Library,
    // Deliberately thread-confined. C ABI callers may synchronize separately.
    _not_send_sync: PhantomData<Rc<()>>,
}
impl Drop for Policy {
    fn drop(&mut self) {
        unsafe {
            (self.close)(self.handle.as_ptr());
        }
    }
}
impl Policy {
    pub fn load(dll: impl AsRef<Path>, model: impl AsRef<Path>) -> Result<Self, String> {
        let dll = dll.as_ref().canonicalize().map_err(|e| e.to_string())?;
        let wide: Vec<u16> = OsStr::new(&dll).encode_wide().chain(Some(0)).collect();
        let module =
            NonNull::new(unsafe { LoadLibraryExW(wide.as_ptr(), ptr::null_mut(), 0x100 | 0x800) })
                .ok_or_else(|| {
                    format!("LoadLibraryExW failed: {}", std::io::Error::last_os_error())
                })?;
        let library = Library(module);
        macro_rules! load {
            ($name:literal,$ty:ty) => {{
                let name = CStr::from_bytes_with_nul(concat!($name, "\0").as_bytes()).unwrap();
                unsafe { std::mem::transmute::<*mut c_void, $ty>(library.symbol(name)?) }
            }};
        }
        let version = load!("tm2020_policy_version", Version);
        if unsafe { version() } != 1 {
            return Err("Unsupported policy ABI version".into());
        }
        let open = load!("tm2020_policy_open", Open);
        let close = load!("tm2020_policy_close", Close);
        let get_info = load!("tm2020_policy_get_info", GetInfo);
        let predict = load!("tm2020_policy_predict", Predict);
        let get_schema = load!("tm2020_policy_schema", Schema);
        let last_error = load!("tm2020_policy_last_error", LastError);
        let path = CString::new(model.as_ref().to_str().ok_or("Model path must be UTF-8")?)
            .map_err(|e| e.to_string())?;
        let mut raw = ptr::null_mut();
        if unsafe { open(path.as_ptr(), &mut raw) } != 0 {
            return Err(error(last_error));
        }
        let handle = NonNull::new(raw).ok_or("Native DLL returned a null policy")?;
        let mut info = Info {
            size_bytes: std::mem::size_of::<Info>() as u32,
            api_version: 1,
            ..Info::default()
        };
        let status = unsafe { get_info(handle.as_ptr(), &mut info) };
        if status != 0
            || info.observations == 0
            || info.observations > 4096
            || info.actions == 0
            || info.actions > 64
            || info.reserved != 0
        {
            unsafe {
                close(handle.as_ptr());
            }
            return Err("Invalid native policy dimensions".into());
        }
        let schema_ptr = unsafe { get_schema(handle.as_ptr()) };
        if schema_ptr.is_null() {
            unsafe {
                close(handle.as_ptr());
            }
            return Err("Missing observation schema".into());
        }
        let schema = unsafe { CStr::from_ptr(schema_ptr) }
            .to_string_lossy()
            .into_owned();
        Ok(Self {
            handle,
            close,
            predict,
            last_error,
            observations: info.observations as usize,
            actions: info.actions as usize,
            schema,
            _library: library,
            _not_send_sync: PhantomData,
        })
    }
    pub fn observation_count(&self) -> usize {
        self.observations
    }
    pub fn action_count(&self) -> usize {
        self.actions
    }
    pub fn observation_schema(&self) -> &str {
        &self.schema
    }
    pub fn predict(&self, schema: &str, observations: &[f64]) -> Result<(Vec<f64>, f64), String> {
        let mut actions = vec![0.; self.actions];
        let value = self.predict_into(schema, observations, &mut actions)?;
        Ok((actions, value))
    }
    /// Allocation-free inference into caller-owned storage. On error, actions
    /// are cleared; callers must still treat an error as no actuation.
    pub fn predict_into(
        &self,
        schema: &str,
        observations: &[f64],
        actions: &mut [f64],
    ) -> Result<f64, String> {
        actions.fill(0.);
        if schema != self.schema {
            return Err("Observation schema mismatch".into());
        }
        if observations.len() != self.observations
            || actions.len() != self.actions
            || observations.iter().any(|x| !x.is_finite())
        {
            return Err("Observation count or finite-value check failed".into());
        }
        let mut value = 0.;
        let status = unsafe {
            (self.predict)(
                self.handle.as_ptr(),
                observations.as_ptr(),
                self.observations as u32,
                actions.as_mut_ptr(),
                self.actions as u32,
                &mut value,
            )
        };
        if status != 0 {
            return Err(error(self.last_error));
        }
        if !value.is_finite() || actions.iter().any(|a| !a.is_finite() || a.abs() > 1.) {
            return Err("Invalid native policy output".into());
        }
        Ok(value)
    }
}
fn error(f: LastError) -> String {
    let p = unsafe { f() };
    if p.is_null() {
        "Native policy error".into()
    } else {
        unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned()
    }
}

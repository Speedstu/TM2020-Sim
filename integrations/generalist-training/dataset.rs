use anyhow::{Result,ensure};
use std::path::Path;
fn main()->Result<()>{let a:Vec<_>=std::env::args().collect();ensure!(a.len()==5,"dataset MAP PACKS REPLAY OUTPUT.csv");
 println!("{}",tm2020_generalist::export_demonstration(Path::new(&a[1]),Path::new(&a[2]),Path::new(&a[3]),Path::new(&a[4]))?);Ok(())}

use anyhow::{Result,ensure};
use std::path::Path;
fn main()->Result<()>{
    let a:Vec<_>=std::env::args().collect();
    ensure!(a.len()==9,"fast-dataset MAP PACKS ROUTE REPLAY OUTPUT.csv LOOKAHEAD GAIN RESIDUAL");
    let r=tm2020_fast::export_demonstration(Path::new(&a[1]),Path::new(&a[2]),Path::new(&a[3]),
        Path::new(&a[4]),Path::new(&a[5]),a[6].parse()?,a[7].parse()?,a[8].parse()?)?;
    println!("{}",serde_json::to_string_pretty(&r)?);Ok(())
}

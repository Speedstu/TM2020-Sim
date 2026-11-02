use tm2020_sdk::Policy;
fn main() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 4 {
        return Err("policy DLL MODEL comma-separated-observations".into());
    }
    let policy = Policy::load(&args[1], &args[2])?;
    let x: Vec<f64> = args[3]
        .split(',')
        .map(|x| x.parse().map_err(|e| format!("{e}")))
        .collect::<Result<_, _>>()?;
    let (actions, value) = policy.predict(policy.observation_schema(), &x)?;
    if policy.predict("wrong_schema", &x).is_ok() {
        return Err("Schema mismatch was accepted".into());
    }
    let mut invalid = x.clone();
    invalid[0] = f64::NAN;
    if policy
        .predict(policy.observation_schema(), &invalid)
        .is_ok()
    {
        return Err("NaN was accepted".into());
    }
    println!("RUST_POLICY schema={} actions={:?} value={} schema_rejection=true nonfinite_rejection=true",policy.observation_schema(),actions,value);
    Ok(())
}

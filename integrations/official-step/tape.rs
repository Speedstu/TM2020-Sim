// SPDX-License-Identifier: MIT
// Use the upstream codec, never a second implementation of ghost bitstreams.
use fk::tape::Tape;
use std::path::Path;

fn run() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 && args.len() != 5 {
        return Err("usage: tm2020-official-tape info INPUT | patch INPUT EDITS.tsv OUTPUT.Ghost.Gbx".into());
    }
    let tape = Tape::load(&args[2])?;
    tape.codec_is_lossless()?;
    if args[1] == "info" && args.len() == 3 {
        println!("{{\"ticks\":{},\"startOffsetMs\":{},\"declaredMs\":{}}}", tape.n(),
                 tape.start_offset_ms, tape.declared_ms.map_or("null".into(), |v| v.to_string()));
        return Ok(());
    }
    if args[1] == "dump" && args.len() == 3 {
        println!("index,race_ms,steer_i8,gas,brake");
        for i in 0..tape.n() {
            println!("{},{},{},{},{}",i,tape.race_ms(i),tape.steer[i] as i8,tape.accel[i],tape.brake[i]);
        }
        return Ok(());
    }
    if args[1] == "modes" && args.len()==3 {
        let raw=gbx::tape::Tape::from_file(&args[2])?;
        for (i,p) in raw.archives[0].packets.iter().enumerate(){
            if i==0 || p.mode!=raw.archives[0].packets[i-1].mode {
                println!("{i} mode={} word0={} flags={}",p.mode,p.word0,p.flags);
            }
        }
        return Ok(());
    }
    let activate=args[1]=="patch-active";
    if (args[1] != "patch" && !activate) || args.len() != 5 {
        return Err("unsupported tape command".into());
    }
    if Path::new(&args[4]).exists() { return Err("never overwrite a ghost".into()); }
    let (mut steer, mut gas, mut brake) = (tape.steer.clone(), tape.accel.clone(), tape.brake.clone());
    let text = std::fs::read_to_string(&args[3]).map_err(|e| e.to_string())?;
    let mut seen = std::collections::BTreeSet::new();
    for (row, line) in text.lines().enumerate() {
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.len() != 4 { return Err(format!("edit {}: expected index steer_i8 gas_bit brake_bit", row)); }
        let i: usize = fields[0].parse::<usize>().map_err(|e|e.to_string())?;
        let s: i8 = fields[1].parse::<i8>().map_err(|e|e.to_string())?;
        let g: u8 = fields[2].parse::<u8>().map_err(|e|e.to_string())?;
        let b: u8 = fields[3].parse::<u8>().map_err(|e|e.to_string())?;
        if i >= tape.n() || s == -128 || g > 1 || b > 1 || !seen.insert(i) {
            return Err(format!("invalid or duplicate edit at row {}", row));
        }
        steer[i] = s as u8; gas[i] = g; brake[i] = b;
    }
    let mut activated=0;
    if activate {
        use gbx::tape::{Tape as RawTape,Encoding,StateEnc,literal_for};
        let mut raw=RawTape::from_file(&args[2])?;
        let mut last=None;
        for (i,p) in raw.archives[0].packets.iter_mut().enumerate(){
            if matches!(p.mode,2|4|12){last=Some(p.clone());}
            if seen.contains(&i) && matches!(p.mode,0|15) {
                let template=last.as_ref().ok_or("no active vehicle packet before inactive tail")?;
                p.word0=template.word0 & !0x20;p.flags=template.flags;p.mode=template.mode;
                p.state=StateEnc::Lit(literal_for(p.word0,p.flags));activated+=1;
            }
            if seen.contains(&i) && !matches!(p.mode,2|4|12){return Err(format!("unsupported vehicle packet mode {} at {i}",p.mode));}
            p.steer=steer[i] as u32;p.accel=gas[i] as u32;p.brake=brake[i] as u32;p.vsame=false;
        }
        let container=gbx::container::Container::load(&args[2])?;
        std::fs::write(&args[4],raw.inject_into(&container,Encoding::Explicit)?).map_err(|e|e.to_string())?;
    } else {
        tape.write_candidate(&steer, &gas, &brake, Path::new(&args[4]))?;
    }
    let checked = Tape::load(&args[4])?;
    if checked.steer != steer || checked.accel != gas || checked.brake != brake ||
        checked.start_offset_ms != tape.start_offset_ms {
        return Err("written tape failed independent decode".into());
    }
    println!("{{\"edits\":{},\"ticks\":{},\"activatedTailPackets\":{},\"decodedWriteVerified\":true}}", seen.len(), tape.n(),activated);
    Ok(())
}
fn main() {
    if let Err(error) = run() { eprintln!("official-tape: {}", error); std::process::exit(1); }
}

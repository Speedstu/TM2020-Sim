// SPDX-License-Identifier: GPL-3.0-or-later
// Independently tested enqueue kernel. Not wired into Dyna's unfinished
// activation consumer; doing so would not qualify that later callback.
use anyhow::{Result,ensure};
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Index {pub rest_since:u32,pub active_index:u16,pub reserved:u8,pub queued:u8}
pub fn request(enabled:bool,slot:usize,indices:&mut[Index],reverse:&[u32],pending:&mut Vec<u32>)->Result<bool>{
    if !enabled{return Ok(false);}
    ensure!(slot<indices.len(),"wake index bound");let state=&mut indices[slot];
    if state.active_index!=u16::MAX||state.queued==1{return Ok(false);}
    ensure!(slot<reverse.len()&&pending.len()<65535,"wake map/queue bound");
    pending.push(reverse[slot]);state.queued=1;Ok(true)
}

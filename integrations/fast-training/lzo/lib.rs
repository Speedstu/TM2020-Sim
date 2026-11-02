//! Safe-size adapter to system liblzo2 for local GBX decompression.
//! No compression implementation or substitute byte stream is provided.
use std::ffi::c_void;
#[link(name="liblzo2.so.2",kind="dylib",modifiers="+verbatim")]
unsafe extern "C" {
    fn lzo1x_decompress_safe(src:*const u8,src_len:usize,dst:*mut u8,dst_len:*mut usize,work:*mut c_void)->i32;
}
#[derive(Debug)]
pub struct Error(pub i32);
pub fn decompress_all(data:&[u8],size:Option<usize>)->Result<Vec<u8>,Error>{
    let size=size.filter(|n|*n<=512*1024*1024).ok_or(Error(-10))?;
    let mut output=vec![0u8;size];let mut actual=size;
    let status=unsafe{lzo1x_decompress_safe(data.as_ptr(),data.len(),output.as_mut_ptr(),&mut actual,std::ptr::null_mut())};
    if status!=0 || actual!=size{return Err(Error(status));}
    Ok(output)
}

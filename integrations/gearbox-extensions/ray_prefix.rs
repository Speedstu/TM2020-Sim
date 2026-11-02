    let fraction = if two_sided {
        // 0x1af404: endpoint plane distance has X/Y/Z order, unlike origin Y/X/Z.
        let end = ((origin.x + direction.x) * normal.x
            + (origin.y + direction.y) * normal.y)
            + (origin.z + direction.z) * normal.z + tri.offset;
        // Original sign-bit XOR, not a geometric <= 0 comparison.
        if ((end.to_bits() ^ plane_distance.to_bits()) & 0x80000000) == 0 {
            return None;
        }
        safe_div(plane_distance, end - plane_distance)?.abs()
    } else {
        if 0.0 > plane_distance {
            return None;
        }
        let approach = -(normal.x * direction.x + normal.y * direction.y + normal.z * direction.z);
        if plane_distance > approach {
            return None;
        }
        safe_div(plane_distance, approach)?
    };

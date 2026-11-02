using GBX.NET;
using GBX.NET.Engines.GameData;
using GBX.NET.Engines.Plug;
using System.Reflection;

internal static class ItemLab
{
    public static object ExportMeshes(string path, string dir)
    {
        Directory.CreateDirectory(dir);
        var item = Gbx.ParseNode<CGameItemModel>(path);
        if (item is null) throw new InvalidDataException("Not an item");
        var properties = item.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Select(p => {
                object? v = null;
                try { v=p.GetValue(item); } catch {}
                return new {p.Name, type=p.PropertyType.FullName, valueType=v?.GetType().FullName, valuePreview=SafePreview(v)};
            }).ToArray();

        var crystals = new List<(string,CPlugCrystal)>();
        foreach(var p in item.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
            object? v; try { v=p.GetValue(item); } catch { continue; }
            if (v is CPlugCrystal crystal) crystals.Add((p.Name,crystal));
            if(v is null)continue;
            if(p.Name.Contains("Model") || p.Name.Contains("Variant")) {
                var meshProp=v.GetType().GetProperty("MeshCrystal");
                if(meshProp?.GetValue(v) is CPlugCrystal mesh)crystals.Add((p.Name+"_mesh",mesh));
                var variantsProp=v.GetType().GetProperty("CustomizedVariants");
                if(variantsProp?.GetValue(v) is System.Collections.IDictionary dict) {
                    foreach(System.Collections.DictionaryEntry entry in dict) {
                        if(entry.Value is CPlugCrystal c)crystals.Add(($"{p.Name}_variant_{entry.Key}",c));
                    }
                }
            }
        }
        var outputs=new List<object>();
        foreach(var (name,crystal) in crystals) {
            var safeName=string.Concat(name.Select(ch=>char.IsLetterOrDigit(ch)||ch=='_'?ch:'_'));
            var objPath=Path.Combine(dir,safeName+".obj");
            var mtlPath=Path.Combine(dir,safeName+".mtl");
            using var o=new StreamWriter(objPath);
            using var m=new StreamWriter(mtlPath);
            crystal.ExportToObj(o,m);
            o.Flush();m.Flush();
            outputs.Add(new {sourceName=name,obj=Path.GetFileName(objPath),
                mtl=Path.GetFileName(mtlPath),objBytes=new FileInfo(objPath).Length});
        }
        var staticObject = item.EntityModel?.GetType().GetProperty("StaticObject")?.GetValue(item.EntityModel);
        var shape = staticObject?.GetType().GetProperty("Shape")?.GetValue(staticObject) as CPlugSurface;
        var trigger = item.EntityModel?.GetType().GetProperty("TriggerShape")?.GetValue(item.EntityModel) as CPlugSurface;
        var solid2 = staticObject?.GetType().GetProperty("Mesh")?.GetValue(staticObject);
        bool isMeshCollidable = staticObject?.GetType().GetProperty("IsMeshCollidable")?.GetValue(staticObject) is true;
        var exportedSurfaces = new List<object>();
        if (shape != null) exportedSurfaces.Add(ExportSurface(shape,dir,"physical_shape"));
        if (trigger != null) exportedSurfaces.Add(ExportSurface(trigger,dir,"trigger_shape"));
        return new {
            kind="item_mesh_export",
            isMeshCollidable,
            visualMeshAvailable = solid2 != null,
            physicalShapeAvailable = shape != null,
            triggerShapeAvailable = trigger != null,
            surfaceExports=exportedSurfaces,
            physicalMaterialSamples = shape?.Materials?.Take(5).Select(m=>DescribeProperties(m)).ToArray(),
            firstVisualProperties = DescribeProperties((solid2?.GetType().GetProperty("Visuals")?.GetValue(solid2) as Array) is { Length: > 0 } vis ? vis.GetValue(0) : null),
            firstShadedGeomProperties = DescribeProperties((solid2?.GetType().GetProperty("ShadedGeoms")?.GetValue(solid2) as Array) is { Length: > 0 } geoms ? geoms.GetValue(0) : null),
            source=path,crystals=crystals.Count,
            caveat="Crystal may describe visual geometry, not a physical collision mesh",
            extracted=outputs,
            properties,
            entityModelProperties = DescribeProperties(item.EntityModel),
            staticObjectProperties = DescribeProperties(
                item.EntityModel?.GetType().GetProperty("StaticObject")?.GetValue(item.EntityModel)),
            triggerShapeProperties = DescribeProperties(
                item.EntityModel?.GetType().GetProperty("TriggerShape")?.GetValue(item.EntityModel)),
            triggerSurfaceMeshProperties = DescribeProperties(
                item.EntityModel?.GetType().GetProperty("TriggerShape")?.GetValue(item.EntityModel) is { } surface
                    ? surface.GetType().GetProperty("Surf")?.GetValue(surface) : null),
            staticMeshProperties = DescribeProperties(
                item.EntityModel?.GetType().GetProperty("StaticObject")?.GetValue(item.EntityModel) is { } sobj
                    ? sobj.GetType().GetProperty("Mesh")?.GetValue(sobj) : null),
            triggerTriangleProperties = DescribeProperties(
                item.EntityModel?.GetType().GetProperty("TriggerShape")?.GetValue(item.EntityModel) is { } surf
                  ? surf.GetType().GetProperty("Surf")?.GetValue(surf) is { } triggerMesh
                    ? (triggerMesh.GetType().GetProperty("Triangles")?.GetValue(triggerMesh) as Array) is {Length: > 0} triArr ? triArr.GetValue(0) : null : null
                  : null)
        };
    }

    private static object ExportSurface(CPlugSurface shape,string dir,string name)
    {
        var surf=shape.Surf as CPlugSurface.Mesh;
        if(surf is null)return new { name, error="No mesh surface",vertices=0,triangles=0 };
        var vertices=surf.Vertices ?? [];
        var triangles=surf.Triangles ?? [];
        string objPath=Path.Combine(dir,name+".obj");
        using(var writer = new StreamWriter(objPath,false,System.Text.Encoding.UTF8))
        {
            writer.WriteLine("# CPlugSurface geometry - local item coordinate space");
            writer.WriteLine("# type="+name+"; NOT necessarily drivable ground");
            foreach(var v in vertices)
                writer.WriteLine(FormattableString.Invariant($"v {v.X:R} {v.Y:R} {v.Z:R}"));
            foreach(var tri in triangles)
            {
                var i=tri.Indices;
                if(i.X<0||i.Y<0||i.Z<0||i.X>=vertices.Length||i.Y>=vertices.Length||i.Z>=vertices.Length)
                    throw new InvalidDataException("Surface triangle index outside vertex array");
                writer.WriteLine($"f {i.X+1} {i.Y+1} {i.Z+1}");
            }
        }
        return new {name,vertices=vertices.Length,triangles=triangles.Length,obj=Path.GetFileName(objPath)};
    }

    private static object[]? DescribeProperties(object? node)
    {
        if(node is null)return null;
        return node.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)
            .Select(p=> {
                object? v=null; try {v=p.GetValue(node);}catch{}
                return (object)new {p.Name,type=p.PropertyType.FullName,valueType=v?.GetType().FullName,valuePreview=SafePreview(v)};
            }).ToArray();
    }
    private static string SafePreview(object? v)
    {
        if(v==null)return "null";
        if(v is byte[] b)return "bytes="+b.Length;
        if(v is string s) return s.Length>150?s[..150]:s;
        if(v is System.Collections.ICollection c)return "collection "+c.Count;
        return v.GetType().Name;
    }
}

using GBX.NET;
using GBX.NET.Engines.Game;
using GBX.NET.LZO;
using GBX.NET.ZLib;
using System.Text.Json;
using System.Security.Cryptography;
using System.Reflection.PortableExecutable;
using System.Text;
using System.IO.Compression;

Gbx.LZO = new Lzo();
Gbx.ZLib = new ZLib();
var jsonOptions = new JsonSerializerOptions { WriteIndented = true };

if (args.Length < 2 || !new[] { "map", "scan", "replay", "record-schema", "dataset", "map-schema", "embedded", "embedded-extract", "mesh-extract", "pe", "pak" }.Contains(args[0].ToLowerInvariant()))
{
    Console.WriteLine("Usage:\n  GbxLab map <file.Map.Gbx> [out.json]\n  GbxLab replay <file.Replay.Gbx> [out.json]\n  GbxLab scan <map-folder> [out.json]\n  GbxLab pe <Trackmania.exe> [out.json]\n  GbxLab pak <file.pak> [out.json]");
    return 2;
}
string command = args[0].ToLowerInvariant();
string path = Path.GetFullPath(args[1]);
string? output = args.Length >= 3 ? Path.GetFullPath(args[2]) : null;
try
{
    object result;
    if (command == "scan")
    {
        if (!Directory.Exists(path)) throw new DirectoryNotFoundException(path);
        var records = new List<object>();
        var errors = new List<object>();
        foreach (var file in Directory.EnumerateFiles(path, "*.Gbx", SearchOption.AllDirectories)
            .Where(p => p.EndsWith(".Map.Gbx", StringComparison.OrdinalIgnoreCase) ||
                        p.EndsWith(".Challenge.Gbx", StringComparison.OrdinalIgnoreCase)))
        {
            try { records.Add(ParseMap(file)); }
            catch (Exception e) { errors.Add(new { file, error = e.Message }); }
        }
        result = new { kind = "map_scan", directory = path, count = records.Count, errors = errors.Count, records, failures = errors };
    }
    else if (command == "map") result = ParseMap(path);
    else if (command == "replay") result = ParseReplay(path);
    else if (command == "record-schema") result = InspectRecordSchema(path);
    else if (command == "dataset") result = ReplayDataset.Export(path);
    else if (command == "map-schema") result = InspectMapSchema(path);
    else if (command == "embedded" || command == "embedded-extract")
    {
        if (command == "embedded-extract" && output == null)
            throw new ArgumentException("embedded-extract requires output folder as third argument");
        result = InspectEmbedded(path, command == "embedded-extract" ? output : null);
        if (command == "embedded-extract") output = Path.Combine(output!, "manifest.json");
    }
    else if (command == "mesh-extract")
    {
        if (output == null) throw new ArgumentException("mesh-extract requires a destination folder");
        result = ItemLab.ExportMeshes(path,output);
        output = Path.Combine(output,"manifest.json");
    }
    else if (command == "pe") result = InspectPE(path);
    else result = InspectPak(path);

    string json = JsonSerializer.Serialize(result, jsonOptions);
    if (output is not null)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        File.WriteAllText(output, json);
        Console.WriteLine("WROTE " + output);
    }
    else Console.WriteLine(json);
    return 0;
}
catch (Exception e)
{
    Console.Error.WriteLine($"ERROR: {e.GetType().Name}: {e.Message}");
    return 1;
}

static object InspectEmbedded(string file, string? extractFolder)
{
    var map = Gbx.ParseNode<CGameCtnChallenge>(file);
    byte[] bytes = map.EmbeddedZipData ?? Array.Empty<byte>();
    if (bytes.Length == 0) return new { kind = "embedded", file, archiveBytes=0, entries=Array.Empty<object>(), extracted=0 };
    using var compressed = new MemoryStream(bytes,false);
    using var archive = new ZipArchive(compressed,ZipArchiveMode.Read,false);
    const long maxOne = 30*1024*1024;
    const long maxTotal = 150*1024*1024;
    if (archive.Entries.Count > 4000) throw new InvalidDataException("Excess entries in embedded archive");
    long total=0;
    var records = new List<object>();
    int extracted=0;
    foreach(var item in archive.Entries) {
        if (string.IsNullOrWhiteSpace(item.Name)) continue;
        if(item.Length < 0 || item.Length > maxOne) throw new InvalidDataException("Oversized embedded entry");
        total+=item.Length;
        if(total > maxTotal) throw new InvalidDataException("Excess total uncompressed data");
        var name=item.FullName.Replace('\\','/');
        if (name.StartsWith("/") || name.Split('/').Any(p=>p==".." || p==".") || name.Contains(':'))
            throw new InvalidDataException("Invalid embedded entry path");
        records.Add(new {entry=name, bytes=item.Length, compressedBytes=item.CompressedLength});
        if(extractFolder is not null) {
            string root=Path.GetFullPath(extractFolder);
            string full=Path.GetFullPath(Path.Combine(root,name.Replace('/',Path.DirectorySeparatorChar)));
            if(!full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Path escapes output folder");
            Directory.CreateDirectory(Path.GetDirectoryName(full)!);
            using var input=item.Open();
            using var output=File.Create(full);
            input.CopyTo(output);
            extracted++;
        }
    }
    return new {kind="embedded",file,archiveBytes=bytes.Length,entriesCount=records.Count,unpackedBytes=total,extracted,entries=records.ToArray()};
}

static object InspectMapSchema(string file)
{
    var map = Gbx.ParseNode<CGameCtnChallenge>(file);
    return new {
        kind = "map_schema",
        file,
        embedded = map?.GetType().GetProperties()
           .Where(p => p.Name.Contains("Embed",StringComparison.OrdinalIgnoreCase) ||
                       p.Name.Contains("Pack",StringComparison.OrdinalIgnoreCase) ||
                       p.Name.Contains("Item",StringComparison.OrdinalIgnoreCase) ||
                       p.Name.Contains("Zip",StringComparison.OrdinalIgnoreCase) ||
                       p.Name.Contains("Snap",StringComparison.OrdinalIgnoreCase))
           .Select(p => new {
               p.Name, type=p.PropertyType.FullName,
               value=GetDescription(p.GetValue(map))
           }).ToArray(),
        anchoredItemModel = map?.GetAnchoredObjects().Take(5).Select(a => new {
            model=a.ItemModel.ToString(),
            objectProperties=a.GetType().GetProperties()
                .Where(p=>p.Name.Contains("Model")||p.Name.Contains("Item"))
                .Select(p=>new {p.Name,type=p.PropertyType.FullName,value=GetDescription(p.GetValue(a))}).ToArray()
        }).ToArray()
    };
}
static string GetDescription(object? obj)
{
    if (obj is null) return "null";
    if (obj is byte[] bytes) return "bytes="+bytes.Length;
    if (obj is System.Collections.ICollection c) return "collection count="+c.Count;
    return obj.ToString() ?? "null";
}
static object InspectRecordSchema(string file)
{
    var replay = Gbx.ParseNode<CGameCtnReplayRecord>(file);
    var rd = replay?.RecordData ?? replay?.GetGhosts().FirstOrDefault()?.RecordData;
    if (rd is null) return new { kind = "record_schema", found = false };
    var entries = rd.EntList;
    var descs = rd.EntRecordDescs;
    return new {
        kind = "record_schema",
        found = true,
        start = rd.Start.ToString(),
        end = rd.End.ToString(),
        recordEntitiesCount = entries.Count,
        descriptorCount = descs.Length,
        descriptors = descs.Select(d => new {
           classId = d.ClassId.ToString("X8"),
           type = d.GetType().FullName,
           fields = d.GetType().GetProperties().Select(p => new {
              p.Name, type = p.PropertyType.FullName,
              value = p.GetValue(d) is byte[] b ? $"byte[{b.Length}]" : p.GetValue(d)?.ToString()
           }).ToArray()
        }).ToArray(),
        entities = entries.Select(e => new {
           entType = e.Type,
           samplesCount = e.Samples?.Count ?? 0,
           samples2Count = e.Samples2?.Count ?? 0,
           firstSamples = e.Samples?.Take(2).Select(s => new {
              type = s.GetType().FullName,
              fields = s.GetType().GetProperties().Select(p => new {
                  p.Name, type = p.PropertyType.FullName,
                  value = p.GetValue(s) is byte[] b ? $"byte[{b.Length}] {Convert.ToHexString(b.AsSpan(0,Math.Min(32,b.Length)))}" : p.GetValue(s)?.ToString()
              }).ToArray()
           }).ToArray(),
           firstSamples2 = e.Samples2?.Take(2).Select(s => new {
              type = s.GetType().FullName,
              fields = s.GetType().GetProperties().Select(p => new {
                  p.Name, type = p.PropertyType.FullName,
                  value = p.GetValue(s) is byte[] b ? $"byte[{b.Length}] {Convert.ToHexString(b.AsSpan(0,Math.Min(32,b.Length)))}" : p.GetValue(s)?.ToString()
              }).ToArray()
           }).ToArray()
        }).ToArray()
    };
}

static object InspectPE(string file)
{
    using var stream = File.OpenRead(file);
    using var reader = new PEReader(stream);
    var coff = reader.PEHeaders.CoffHeader;
    var optional = reader.PEHeaders.PEHeader;
    return new {
        kind = "pe_static",
        file,
        machine = coff.Machine.ToString(),
        coffTimestamp = coff.TimeDateStamp,
        imageBase = optional?.ImageBase,
        imageSize = optional?.SizeOfImage,
        executableEntryPointRva = optional?.AddressOfEntryPoint,
        nativeSections = reader.PEHeaders.SectionHeaders.Select(s => new {
            name = s.Name, virtualAddress = s.VirtualAddress, virtualSize = s.VirtualSize,
            rawOffset = s.PointerToRawData, rawSize = s.SizeOfRawData,
            flags = s.SectionCharacteristics.ToString()
        }).ToArray()
    };
}

static object InspectPak(string file)
{
    using var stream = File.OpenRead(file);
    using var reader = new BinaryReader(stream);
    if (stream.Length < 12) throw new InvalidDataException("Short file");
    var magic = Encoding.ASCII.GetString(reader.ReadBytes(8));
    if (magic != "NadeoPak") throw new InvalidDataException("Not a NadeoPak archive");
    int version = reader.ReadInt32();
    return new {
        kind = "nadeopak_header_only",
        file, bytes = stream.Length, magic, version,
        note = "Archive content is not extracted. No decryption or protected content handling."
    };
}

static object ParseMap(string file)
{
    var map = Gbx.ParseNode<CGameCtnChallenge>(file);
    if (map == null) throw new InvalidDataException("Map parse returned null");
    var blocks = map.GetBlocks().Select(b => new {
        name = b.Name,
        grid = new[] { b.Coord.X, b.Coord.Y, b.Coord.Z },
        direction = b.Direction.ToString(),
        isGround = b.IsGround,
        isFree = b.IsFree,
        flags = b.Flags,
        variant = b.Variant,
        subVariant = b.SubVariant,
        absolutePositionInMap = b.AbsolutePositionInMap is { } pos ? new[] { pos.X, pos.Y, pos.Z } : null,
        yawPitchRoll = b.YawPitchRoll is { } rot ? new[] { rot.X, rot.Y, rot.Z } : null
    }).ToArray();
    var items = map.GetAnchoredObjects().Select(a => new {
        model = a.ItemModel.ToString(),
        positionInMap = new[] { a.AbsolutePositionInMap.X, a.AbsolutePositionInMap.Y, a.AbsolutePositionInMap.Z },
        yawPitchRoll = new[] { a.YawPitchRoll.X, a.YawPitchRoll.Y, a.YawPitchRoll.Z }
    }).ToArray();
    return new {
        kind = "map",
        file,
        mapName = map.MapName,
        uid = map.MapUid,
        author = map.AuthorLogin,
        blocksCount = blocks.Length,
        bakedBlocksCount = map.GetBakedBlocks().Count(),
        itemsCount = items.Length,
        coordinateNote = "grid is block grid XYZ, not meter-space collision geometry; absolutePositionInMap is only populated for free blocks",
        blockTypes = blocks.GroupBy(b => b.name).OrderByDescending(g => g.Count())
                         .Select(g => new { name = g.Key, count = g.Count() }).ToArray(),
        items,
        blocks
    };
}

static object ParseReplay(string file)
{
    var node = Gbx.ParseNode(file);
    var ghosts = node switch
    {
        CGameCtnReplayRecord replay => replay.GetGhosts().ToArray(),
        CGameCtnGhost ghost => new[] { ghost },
        _ => Array.Empty<CGameCtnGhost>()
    };
    return new {
        kind = "replay_or_ghost",
        file,
        nodeType = node?.GetType().Name ?? "unknown",
        count = ghosts.Length,
        ghosts = ghosts.Select(g => new {
            raceTime = g.RaceTime.ToString(),
            playerInputGroups = g.PlayerInputs?.Count() ?? 0,
            playerInputs = (g.PlayerInputs ?? []).Select(p => new {
                inputChanges = p.InputChanges.Count,
                timeline = p.InputChanges
                    .OfType<CGameCtnGhost.PlayerInputData.TrackmaniaInputChange>()
                    .Select(change => new {
                        timestamp = change.Time.ToString(),
                        startOffset = p.StartOffset?.ToString(),
                        steerRaw = change.Steer,
                        gas = change.Gas,
                        brake = change.Brake,
                        horn = change.Horn,
                        respawn = change.Respawn
                    }).ToArray()
            }).ToArray()
        }).ToArray()
    };
}

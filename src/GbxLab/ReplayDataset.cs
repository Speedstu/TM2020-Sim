using System.Globalization;
using GBX.NET;
using GBX.NET.Engines.Game;
using GBX.NET.Engines.Scene;

internal static class ReplayDataset
{
    // GBX time strings are race-relative "m:ss.fff". The PlayerInputs StartOffset
    // in TM2020 replays is frequently negative (e.g. -0:00.150).
    public static long ParseTimeMilliseconds(object? value)
    {
        string s = value?.ToString()?.Trim() ?? "0:00.000";
        bool negative = s.StartsWith('-');
        if (negative) s = s[1..];
        string[] parts = s.Split(':');
        long ms;
        if (parts.Length is 2 or 3)
        {
            var last = parts[^1].Split('.');
            long secs = long.Parse(last[0], CultureInfo.InvariantCulture);
            long millis = last.Length > 1 ? long.Parse(last[1].PadRight(3,'0')[..3], CultureInfo.InvariantCulture) : 0;
            long minutes = long.Parse(parts[^2], CultureInfo.InvariantCulture);
            long hours = parts.Length == 3 ? long.Parse(parts[0], CultureInfo.InvariantCulture) : 0;
            ms = ((hours * 60 + minutes) * 60 + secs) * 1000 + millis;
        }
        else
        {
            throw new FormatException("Unsupported GBX clock format: " + s);
        }
        return negative ? -ms : ms;
    }

    internal record InputEvent(long TMs, sbyte? Steer, bool? Gas, bool? Brake, bool? Respawn, int Order);

    public static object Export(string file)
    {
        var node = Gbx.ParseNode(file);
        var ghosts = node switch {
            CGameCtnReplayRecord replay => replay.GetGhosts().ToArray(),
            CGameCtnGhost ghost => new [] { ghost },
            _ => Array.Empty<CGameCtnGhost>()
        };
        if (ghosts.Length == 0) throw new InvalidDataException("No ghost in replay");
        return new {
            schema = "tm2020_replay_dataset_v1",
            sourceReplay = file,
            warning = "Vehicle samples are recorded replay/visual states, not internal physics snapshots. Timeline inputs are held piecewise-constant and offsets are applied.",
            ghosts = ghosts.Select(ExportGhost).ToArray()
        };
    }

    private static object ExportGhost(CGameCtnGhost ghost)
    {
        int order = 0;
        var inputEvents = (ghost.PlayerInputs ?? [])
            .SelectMany(group => {
                long offset = ParseTimeMilliseconds(group.StartOffset);
                return group.InputChanges
                    .OfType<CGameCtnGhost.PlayerInputData.TrackmaniaInputChange>()
                    .Select(e => new InputEvent(
                        ParseTimeMilliseconds(e.Time) + offset,
                        e.Steer, e.Gas, e.Brake, e.Respawn, order++));
            })
            .OrderBy(e => e.TMs)
            .ThenBy(e => e.Order)
            .ToArray();

        var states = ghost.RecordData?.EntList
            .SelectMany(e => e.Samples ?? [])
            .OfType<CSceneVehicleVis.EntRecordDelta>()
            .OrderBy(s => ParseTimeMilliseconds(s.Time))
            .ToArray() ?? [];

        if (states.Length == 0) {
            return new { result = (object)new {
                raceTime = ghost.RaceTime.ToString(),
                stateSamples = 0,
                inputEvents = inputEvents.Length,
                warning = "Ghost has no CSceneVehicleVis samples"
            }};
        }

        bool gas = false, brake = false;
        sbyte steer = 0;
        int index = 0;
        var rows = new List<object>(states.Length);
        foreach(var s in states) {
            long ms = ParseTimeMilliseconds(s.Time);
            // Zero-order hold: apply all player input changes up to vehicle sample time.
            while(index < inputEvents.Length && inputEvents[index].TMs <= ms) {
                var c = inputEvents[index++];
                if(c.Steer.HasValue) steer = c.Steer.Value;
                if(c.Gas.HasValue) gas = c.Gas.Value;
                if(c.Brake.HasValue) brake = c.Brake.Value;
            }
            rows.Add(new {
                tMs = ms,
                position = new[]{s.Position.X,s.Position.Y,s.Position.Z},
                rotation = new[]{s.Rotation.X,s.Rotation.Y,s.Rotation.Z,s.Rotation.W},
                euler = new[]{s.PitchYawRoll.X,s.PitchYawRoll.Y,s.PitchYawRoll.Z},
                velocity = new[]{s.Velocity.X,s.Velocity.Y,s.Velocity.Z},
                speedKmh = s.Speed,
                gear = s.Gear,
                rpmRaw = s.RPM,
                recordedControls = new { steer=s.Steer, gas=s.Gas, brake=s.Brake },
                replayInput = new { steerRaw=steer, gas, brake },
                ground = s.IsGroundContact,
                roofContact = s.IsTopContact,
                sideSpeed = s.SideSpeed,
                tire = new {
                    groundMaterials = new[]{s.FLGroundContactMaterial.ToString(),
                          s.FRGroundContactMaterial.ToString(), s.RLGroundContactMaterial.ToString(),
                          s.RRGroundContactMaterial.ToString()},
                    icing = new[]{s.FLIcing,s.FRIcing,s.RLIcing,s.RRIcing},
                    dirt = new[]{s.FLDirt,s.FRDirt,s.RLDirt,s.RRDirt},
                    suspensionLength = new[]{s.FLDampenLen,s.FRDampenLen,s.RLDampenLen,s.RRDampenLen},
                    slip = new[]{s.FLSlipCoef,s.FRSlipCoef,s.RLSlipCoef,s.RRSlipCoef},
                    wheelRot = new[]{s.FLWheelRot,s.FRWheelRot,s.RLWheelRot,s.RRWheelRot}
                },
                reactor = new { groundMode=s.IsReactorGroundMode, boostLevel=s.ReactorBoostLvl.ToString(), boostType=s.ReactorBoostType.ToString(),
                    steer=s.ReactorAirControlSteer, pedal=s.ReactorAirControlPedal },
                turbo = new {active=s.IsTurbo, time=s.TurboTime},
                wetness = s.WetnessValue,
                simulationTimeCoef=s.SimulationTimeCoef
            });
        }
        return new { result=(object)new {
            raceTime = ghost.RaceTime.ToString(),
            stateSamples = rows.Count,
            inputChanges = inputEvents.Length,
            startMs=rows.Count > 0 ? ParseTimeMilliseconds(states[0].Time) : 0,
            endMs=rows.Count > 0 ? ParseTimeMilliseconds(states[^1].Time) : 0,
            inputEventTimeline = inputEvents.Select(e=>new {tMs=e.TMs,steerRaw=e.Steer,gas=e.Gas,brake=e.Brake,respawn=e.Respawn}).ToArray(),
            stateInputRows = rows
        }};
    }
}

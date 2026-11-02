// Offline research plugin. Not tested in the running game yet.
// Read-only: observes current viewed vehicle, never injects game inputs.
// Sends newline-delimited JSON to a native C++ collector on 127.0.0.1:24826.
// The observed samples arrive on RENDER/PLUGIN updates, not guaranteed physics ticks.
// Start the C++ collector on H: BEFORE enabling the plugin through Settings.
// Openplanet itself may create profile data on C: if installed; do not silently install.
[Setting name="Enable passive physics capture" category="Offline Physics Research"]
bool S_CaptureEnabled = false;
[Setting name="TCP port on 127.0.0.1" category="Offline Physics Research" min=1024 max=65535]
int S_CapturePort = 24826;

Net::Socket@ g_TM2020Socket = null;
uint g_TM2020LastConnectAttempt = 0;
uint64 g_TM2020Sequence = 0;
uint g_TM2020LastTelemetryAt = 0;

void TM2020Close()
{
    if (g_TM2020Socket !is null) {
        try { g_TM2020Socket.Close(); } catch {}
    }
    @g_TM2020Socket = null;
}

void OnDisabled() { TM2020Close(); }
void OnDestroyed() { TM2020Close(); }
void Main() { print("TM2020 Physics Lab: passive capture available in plugin settings; disabled by default"); }

Json::Value TM2020Vec3(const vec3 &in v)
{
    Json::Value a = Json::Array();
    a.Add(v.x); a.Add(v.y); a.Add(v.z);
    return a;
}

void Update(float dt)
{
    if (!S_CaptureEnabled) { TM2020Close(); return; }

    auto app = GetApp();
    if (app is null || app.CurrentPlayground is null) return; // no menu observations
    auto state = VehicleState::ViewingPlayerState();
    if (state is null) return;

    if (g_TM2020Socket is null) {
        if (Time::Now - g_TM2020LastConnectAttempt < 2000) return;
        g_TM2020LastConnectAttempt = Time::Now;
        @g_TM2020Socket = Net::Socket();
        bool connected = false;
        try {
            connected = g_TM2020Socket.Connect("127.0.0.1", uint16(S_CapturePort), false);
        } catch { connected = false; }
        if (!connected) { TM2020Close(); return; }
        print("TM2020 Physics Lab: collector connected at 127.0.0.1:" + S_CapturePort);
    }

    Json::Value row = Json::Object();
    row["schema"] = "tm2020_live_telemetry_v1";
    row["wallMs"] = uint(Time::Now);
    row["sequence"] = uint(g_TM2020Sequence++);
    row["frameDt"] = dt;
    row["raceStartMs"] = int(state.RaceStartTime);
    row["simulationTimeCoef"] = state.SimulationTimeCoef;
    auto map = cast<CGameCtnChallenge>(app.RootMap);
    if (map !is null && map.MapInfo !is null) row["mapUid"] = map.MapInfo.MapUid;
    row["position"] = TM2020Vec3(state.Position);
    row["velocity"] = TM2020Vec3(state.WorldVel);
    row["dir"] = TM2020Vec3(state.Dir);
    row["left"] = TM2020Vec3(state.Left);
    row["up"] = TM2020Vec3(state.Up);
    row["frontSpeed"] = state.FrontSpeed;
    row["sideSpeed"] = VehicleState::GetSideSpeed(state);
    row["steer"] = state.InputSteer;
    row["gas"] = state.InputGasPedal;
    row["brake"] = state.InputBrakePedal;
    row["isBraking"] = state.InputIsBraking;
    row["gear"] = int(state.CurGear);
    row["rpm"] = VehicleState::GetRPM(state);
    row["wetness"] = state.WetnessValue01;
    row["flSlip"] = state.FLSlipCoef;
    row["frSlip"] = state.FRSlipCoef;
    row["rlSlip"] = state.RLSlipCoef;
    row["rrSlip"] = state.RRSlipCoef;
    row["flSteer"] = state.FLSteerAngle;
    row["frSteer"] = state.FRSteerAngle;
    row["flIcing"] = state.FLIcing01;
    row["frIcing"] = state.FRIcing01;

    string json = Json::Write(row) + "\n";
    try {
        g_TM2020Socket.WriteRaw(json);
    } catch {
        TM2020Close();
    }
}

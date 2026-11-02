#pragma once
namespace tm2020::live {
// Shared implementation for the external CLI and explicit injected worker.
// Returns after neutralizing its owned inputs. Does not run from DllMain.
int run_drive_cli(int argc,char** argv);
}

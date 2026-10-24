#include <TiltedOnlinePCH.h>
#include "TiltedOnlineApp.h"
#include <Misc/GameVM.h>
#include <Interface/UI.h>

extern std::unique_ptr<TiltedOnlineApp> g_appInstance;

struct Main;

TP_THIS_FUNCTION(TVMUpdate, int, GameVM, float);
TP_THIS_FUNCTION(TMainLoop, short, Main);
TP_THIS_FUNCTION(TVMDestructor, uintptr_t, void);

static TVMUpdate* VMUpdate = nullptr;
static TMainLoop* MainLoop = nullptr;
static TVMDestructor* VMDestructor = nullptr;

int TP_MAKE_THISCALL(HookVMUpdate, GameVM, float a2)
{
    if (!apThis->IsInactive())
        g_appInstance->Update();

    return TiltedPhoques::ThisCall(VMUpdate, apThis, a2);
}

short TP_MAKE_THISCALL(HookMainLoop, Main)
{
    TP_EMPTY_HOOK_PLACEHOLDER

    auto* pUI = UI::Get();
    const bool cEngineProcessesUI = !pUI || pUI->numPausesGame != 0
        || *(reinterpret_cast<const uint8_t*>(apThis) + 0x16) != 0;
    const short cResult = TiltedPhoques::ThisCall(MainLoop, apThis);
    // 1170 Main+16 is the inactive/loading flag tested by the original UI path.
    UI::ProcessUnpausedMenus(cEngineProcessesUI || *(reinterpret_cast<const uint8_t*>(apThis) + 0x16) != 0);
    return cResult;
}

uintptr_t TP_MAKE_THISCALL(HookVMDestructor, void)
{
    TP_EMPTY_HOOK_PLACEHOLDER

    return TiltedPhoques::ThisCall(VMDestructor, apThis);
}

static TiltedPhoques::Initializer s_mainHooks(
    []()
    {
        POINTER_SKYRIMSE(TMainLoop, cMainLoop, 36564);
        POINTER_SKYRIMSE(TVMUpdate, cVMUpdate, 53926);
        POINTER_SKYRIMSE(TVMDestructor, cVMDestructor, 40412);

        VMUpdate = cVMUpdate.Get();
        MainLoop = cMainLoop.Get();
        VMDestructor = cVMDestructor.Get();

        TP_HOOK(&VMUpdate, HookVMUpdate);
        TP_HOOK(&MainLoop, HookMainLoop);
        TP_HOOK(&VMDestructor, HookVMDestructor);
    });


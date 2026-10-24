#include <Games/Skyrim/Interface/IMenu.h>
#include <Games/Skyrim/Interface/UI.h>
#include <Misc/BSFixedString.h>
#include <TiltedOnlinePCH.h>
#include "immersive_launcher/stubs/DllBlocklist.h"

#include <World.h>
#include <Services/CampaignService.h>
#include <TESObjectREFR.h>
#include <mutex>

namespace
{
bool s_connectedMenusReady = false;
using TSaveGame = bool(void*, uint32_t, uint32_t, const char*);
TSaveGame* RealMenuSave = nullptr;
struct PendingMenuSave
{
    void* Manager{};
    uint32_t Device{}, Stats{};
    String Name;
    bool HasName{}, Pending{};
};
PendingMenuSave s_save;
std::mutex s_saveMutex;
void (*RealLocalMap)(IMenu*, bool) = nullptr;

void UpdateLocalMap(IMenu* apMenu, bool aLocalMap)
{
    RealLocalMap(apMenu, aLocalMap);
    if (UI::ConnectedMenusEnabled())
        apMenu->ClearFlag(IMenu::kFreezeFrameBackground | IMenu::kFreezeFramePause);
}

uintptr_t UpdatePlayerForMap(TESObjectREFR* apPlayer)
{
    const uintptr_t cNode = reinterpret_cast<uintptr_t>(apPlayer->GetNiNode());
    // This call site only tests the result for zero. Keep first-person updates
    // running while the map camera temporarily hides the player node.
    if (cNode)
        return cNode;
    return UI::ConnectedMenusEnabled() && UI::Get()->GetMenuOpen(BSFixedString("MapMenu")) ? 1 : 0;
}

bool QueueMenuSave(void* apManager, uint32_t aDevice, uint32_t aStats, const char* apName)
{
    if (!UI::ConnectedMenusEnabled())
        return RealMenuSave(apManager, aDevice, aStats, apName);

    {
        std::lock_guard lock(s_saveMutex);
        if (s_save.Pending)
            return false;
        s_save = {apManager, aDevice, aStats, apName ? apName : "", apName != nullptr, true};
    }
    // The engine processes this queue at its normal main-thread save boundary.
    POINTER_SKYRIMSE(void(void*, uint32_t), s_requestSave, 35769);
    s_requestSave.Get()(apManager, 0xF0004000);
    spdlog::info("Connected menu: queued manual save");
    return true;
}

void ProcessMenuSave()
{
    PendingMenuSave save;
    {
        std::lock_guard lock(s_saveMutex);
        if (!s_save.Pending)
            return;
        save = s_save;
        // Keep Pending set until the engine finishes; reject a second UI request.
    }
    const bool cSaved = RealMenuSave(save.Manager, save.Device, save.Stats, save.HasName ? save.Name.c_str() : nullptr);
    {
        std::lock_guard lock(s_saveMutex);
        s_save = {};
    }
    spdlog::info("Connected menu: manual save finished, success={}", cSaved);
}

bool Matches(const uint8_t* apSite, std::initializer_list<uint8_t> aBytes)
{
    return std::equal(aBytes.begin(), aBytes.end(), apSite);
}

bool IsSaveBranch(const uint8_t* apSite, uint8_t aOpcode, const void* apTarget)
{
    int32_t displacement{};
    memcpy(&displacement, apSite + 1, sizeof(displacement));
    return apSite[0] == aOpcode && apSite + 5 + displacement == apTarget;
}

bool InstallConnectedMenus()
{
    if (VersionDb::Get().GetLoadedVersionString() != "1.6.1170.0" || stubs::g_IsSoulsREActive)
        return false;

    VersionDbPtr<uint8_t> events(35772), consoleSave(22940), uiSave(52923), entrySave(35533), job(39042), save(35727), playerUpdate(36581), localMap(53112);
    // Validate every instruction before changing any of these related paths.
    if (!IsSaveBranch(consoleSave.Get() + 0xC4, 0xE8, save.Get())
        || !IsSaveBranch(uiSave.Get() + 0x2B, 0xE9, save.Get())
        || !IsSaveBranch(entrySave.Get() + 0x3E, 0xE8, save.Get())
        || !IsSaveBranch(entrySave.Get() + 0x60, 0xE8, save.Get())
        || !Matches(events.Get() + 0x5D5, {0x81, 0xF9, 0x00, 0x08, 0x00, 0xF0, 0x0F, 0x85})
        || !Matches(events.Get() + 0x72A, {0x45, 0x33, 0xF6})
        || !Matches(job.Get() + 0xB, {0x75, 0x25})
        || !Matches(playerUpdate.Get() + 0x7A, {0xFF, 0x90, 0x80, 0x03, 0x00, 0x00, 0x48, 0x85, 0xC0})
        || !Matches(localMap.Get() + 0x9D, {0x89, 0x46, 0x1C}))
    {
        spdlog::error("Connected menus disabled: 1170 save/UI instructions do not match");
        return false;
    }

    // Adapted from Vermunds/SkyrimSoulsRE SaveHandler (GPL-3.0).
    // Unlike the reference stub, ignore unrelated event codes explicitly.
    struct SaveEventCode : TiltedPhoques::CodeGenerator
    {
        SaveEventCode(uint8_t* apEvents) : CodeGenerator(128)
        {
            cmp(ecx, 0xF0000800);
            jne("custom");
            jmp_S(apEvents + 0x5E1);
            L("custom");
            cmp(ecx, 0xF0004000);
            jne("done");
            mov(rax, reinterpret_cast<uintptr_t>(&ProcessMenuSave));
            call(rax); // Existing engine frame provides aligned shadow space.
            L("done");
            jmp_S(apEvents + 0x72A);
        }
    } code(events.Get());
    RealMenuSave = reinterpret_cast<TSaveGame*>(save.Get());
    TiltedPhoques::PutCall(consoleSave.Get() + 0xC4, &QueueMenuSave);
    TiltedPhoques::Jump(uiSave.Get() + 0x2B, &QueueMenuSave);
    TiltedPhoques::PutCall(entrySave.Get() + 0x3E, &QueueMenuSave);
    TiltedPhoques::PutCall(entrySave.Get() + 0x60, &QueueMenuSave);
    TiltedPhoques::Jump(events.Get() + 0x5D5, code.getCode());
    TiltedPhoques::Nop(events.Get() + 0x5DA, 1);

    // Skyrim Souls RE's thread-safety approach: UI work runs after the main
    // loop joins its workers. Keep the job's completion signal intact.
    TiltedPhoques::Put<uint8_t>(job.Get() + 0xB, 0xEB);
    TiltedPhoques::PutCall(playerUpdate.Get() + 0x7A, &UpdatePlayerForMap);
    TiltedPhoques::Nop(playerUpdate.Get() + 0x7F, 1);
    RealLocalMap = reinterpret_cast<decltype(RealLocalMap)>(localMap.Get());
    TP_HOOK(&RealLocalMap, UpdateLocalMap);
    spdlog::info("Connected menus: 1170 deferred saves and main-thread UI installed");
    return true;
}
}

bool UI::ConnectedMenusEnabled() noexcept
{
    return s_connectedMenusReady && !stubs::g_IsSoulsREActive && World::Get().GetTransport().IsConnected();
}

void UI::ProcessUnpausedMenus(bool aMainInactive) noexcept
{
    if (!s_connectedMenusReady || aMainInactive)
        return;
    auto* pUI = Get();
    if (!pUI || pUI->numPausesGame != 0)
        return; // The engine retains its normal paused-menu path.
    POINTER_SKYRIMSE(void(UI*), s_processMessages, 82082);
    POINTER_SKYRIMSE(void(UI*), s_advanceMovies, 82083);
    POINTER_SKYRIMSE(void*(), s_commands, 52950);
    POINTER_SKYRIMSE(void(void*), s_executeCommands, 52952);
    s_processMessages.Get()(pUI);
    s_advanceMovies.Get()(pUI);
    s_executeCommands.Get()(s_commands.Get()());
}

UI* UI::Get()
{
    POINTER_SKYRIMSE(UI*, s_instance, 400327);
    return *s_instance.Get();
}

bool UI::GetMenuOpen(const BSFixedString& acName) const
{
    if (acName.data == nullptr)
        return false;

    TP_THIS_FUNCTION(TMenuSystem_IsOpen, bool, const UI, const BSFixedString&);
    POINTER_SKYRIMSE(TMenuSystem_IsOpen, s_isMenuOpen, 82074);

    return TiltedPhoques::ThisCall(s_isMenuOpen.Get(), this, acName);
}

void UI::CloseAllMenus()
{
    TP_THIS_FUNCTION(TUI_CloseAll, void, const UI);
    POINTER_SKYRIMSE(TUI_CloseAll, s_CloseAll, 82088);

    TiltedPhoques::ThisCall(s_CloseAll.Get(), this);
}

BSFixedString* UI::LookupMenuNameByInstance(IMenu* apMenu)
{
    for (auto& it : menuMap)
    {
        if (it.value.spMenu == apMenu)
            return &it.key;
    }
    return nullptr;
}

IMenu* UI::FindMenuByName(const BSFixedString& acName)
{
    for (const auto& it : menuMap)
    {
        if (it.key == acName)
            return it.value.spMenu;
    }
    return nullptr;
}

void UI::DebugLogAllMenus()
{
    for (auto& e : menuStack)
    {
        spdlog::info("Menu {}", e->uiMenuFlags);
    }
}

static void UnfreezeMenu(IMenu* apEntry)
{
    if (apEntry->PausesGame())
        apEntry->ClearFlag(IMenu::kPausesGame);

    if (apEntry->FreezesBackground())
        apEntry->ClearFlag(IMenu::kFreezeFrameBackground);

    if (apEntry->FreezesFramePause())
        apEntry->ClearFlag(IMenu::kFreezeFramePause);
}

static constexpr const char* kAllowList[] = {
    "TweenMenu",     "MagicMenu",     "StatsMenu",     "InventoryMenu", "MessageBoxMenu",
    "ContainerMenu", "FavoritesMenu", "Tutorial Menu", "Console"
};

static bool ShouldUnpause(UI* apUI, IMenu* apMenu)
{
    auto* pName = apUI->LookupMenuNameByInstance(apMenu);
    if (!pName)
        return false;
    const std::string_view cName(pName->AsAscii());
    // These are engine transitions or shared-rest/checkpoint transactions.
    if (cName == "Loading Menu" || cName == "Main Menu" || cName == "Fader Menu"
        || cName == "Sleep/Wait Menu" || (cName == "Journal Menu" && CampaignService::IsCheckpointActive()))
        return false;
    return true;
}

static void* (*UI_AddToActiveQueue)(UI*, IMenu*, void*);

static void* UI_AddToActiveQueue_Hook(UI* apSelf, IMenu* apMenu, void* apFoundItem /*In reality a reference*/)
{
    // if the menu is empty we let the real function handle it.
    if (!apMenu || !World::Get().GetTransport().IsConnected() || stubs::g_IsSoulsREActive)
        return UI_AddToActiveQueue(apSelf, apMenu, apFoundItem);

#if 0
        if (auto* pName = apSelf->LookupMenuNameByInstance(apEntry))
        {
            spdlog::info("Menu requested {}", pName->AsAscii());
        }
#endif

    if (UI::ConnectedMenusEnabled() && ShouldUnpause(apSelf, apMenu))
    {
        const uint32_t cFlags = apMenu->uiMenuFlags;
        UnfreezeMenu(apMenu);
        if (cFlags != apMenu->uiMenuFlags)
            spdlog::info("Connected menu: unpaused {} flags {:X}->{:X}", apSelf->LookupMenuNameByInstance(apMenu)->AsAscii(), cFlags, apMenu->uiMenuFlags);
        return UI_AddToActiveQueue(apSelf, apMenu, apFoundItem);
    }

    // Retain the original supported menus if the expanded hooks were rejected.
    for (const char* item : kAllowList)
    {
        if (auto* pMenu = apSelf->FindMenuByName(item))
        {
            if (pMenu == apMenu)
                UnfreezeMenu(apMenu);
        }
    }

    return UI_AddToActiveQueue(apSelf, apMenu, apFoundItem);
}

using TCallback = void(void*, const BSFixedString*, uint32_t, void*);
static TCallback* UIMessageQueue__AddMessage_Real;

// Useful for debugging UI related issues.
void UIMessageQueue__AddMessage(void* a1, const BSFixedString* a2, UIMessage::UI_MESSAGE_TYPE a3, void* a4)
{
    spdlog::info("Adding Message {} with prio {} from {}", a2->AsAscii(), a3, fmt::ptr(_ReturnAddress()));
    UIMessageQueue__AddMessage_Real(a1, a2, a3, a4);
}

static TiltedPhoques::Initializer s_s(
    []()
    {
        s_connectedMenusReady = InstallConnectedMenus();
        // pray that this doesnt fail!
        VersionDbPtr<uint8_t> ProcessHook(82082);
        TiltedPhoques::SwapCall(ProcessHook.Get() + 0x682, UI_AddToActiveQueue, &UI_AddToActiveQueue_Hook);

        // Ignore startup movie
        // TODO: Move me later.
        VersionDbPtr<uint8_t> MainInit(36548);
        TiltedPhoques::Put<uint8_t>(MainInit.Get() + 0xFE, 0xEB);

        // Credits to Skyrim Souls RE for this fix.
        // Allows the favorites menu to be numbered during connect.
        VersionDbPtr<uint8_t> FavoritesCanProcess(51538);
        TiltedPhoques::Put<uint16_t>(FavoritesCanProcess.Get() + 0x15, 0x9090);

        // Some experiments:
        // POINTER_SKYRIMSE(TCallback, s_start, 13631);
        // UIMessageQueue__AddMessage_Real = s_start.Get();
        // TP_HOOK(&UIMessageQueue__AddMessage_Real, UIMessageQueue__AddMessage);

        // This kills the loading spinner
        // TiltedPhoques::Put<uint8_t>(0x1405D51C1, 0xEB);
        // TiltedPhoques::Nop(0x1405D51A2, 5);

        // use 8 threads by default!
        // TiltedPhoques::Put<uint8_t>(0x141E45770, 8);
    });

// Address Library AE IDs corroborated by CommonLibSSE-NG UIMessageQueue offsets.
// No additional queue layout is needed: the receiver remains opaque.
bool UI::ShowStatsMenu() noexcept
{
    POINTER_SKYRIMSE(void*, s_queue, 400445);
    void* pQueue = *s_queue.Get();
    if (!pQueue)
        return false;
    using TAddMessage = void(void*, const BSFixedString*, uint32_t, void*);
    POINTER_SKYRIMSE(TAddMessage, s_addMessage, 13631);
    const BSFixedString cMenu("StatsMenu");
    s_addMessage.Get()(pQueue, &cMenu, UIMessage::kShow, nullptr);
    return true;
}

bool UI::HideDialogueMenu() noexcept
{
    POINTER_SKYRIMSE(void*, s_queue, 400445);
    void* pQueue = *s_queue.Get();
    if (!pQueue)
        return false;
    using TAddMessage = void(void*, const BSFixedString*, uint32_t, void*);
    POINTER_SKYRIMSE(TAddMessage, s_addMessage, 13631);
    const BSFixedString cMenu("Dialogue Menu");
    s_addMessage.Get()(pQueue, &cMenu, UIMessage::kHide, nullptr);
    return true;
}

bool UI::CheckpointJournal(bool show) noexcept
{
    // A journal opened before the checkpoint is already on the UI stack.
    // Updating its pause flag therefore also needs to update the UI counter.
    if (show && ConnectedMenusEnabled() && CampaignService::IsCheckpointActive())
    {
        auto* pUI = Get();
        auto* pMenu = pUI ? pUI->FindMenuByName(BSFixedString("Journal Menu")) : nullptr;
        if (pMenu && pUI->GetMenuOpen(BSFixedString("Journal Menu")) && !pMenu->PausesGame())
        {
            pMenu->SetFlag(IMenu::kPausesGame);
            ++pUI->numPausesGame;
        }
    }
    POINTER_SKYRIMSE(void*, queue, 400445);
    if (!*queue.Get()) return false;
    using AddMessage = void(void*, const BSFixedString*, uint32_t, void*);
    POINTER_SKYRIMSE(AddMessage, add, 13631);
    const BSFixedString menu("Journal Menu");
    add.Get()(*queue.Get(), &menu, show ? UIMessage::kShow : UIMessage::kHide, nullptr);
    return true;
}

void UI::FinishCheckpointJournal(bool aClose) noexcept
{
    if (aClose)
    {
        CheckpointJournal(false);
        return;
    }
    auto* pUI = Get();
    if (!ConnectedMenusEnabled() || !pUI || !pUI->GetMenuOpen(BSFixedString("Journal Menu")))
        return;
    auto* pMenu = pUI->FindMenuByName(BSFixedString("Journal Menu"));
    if (pMenu && pMenu->PausesGame() && pUI->numPausesGame > 0)
    {
        pMenu->ClearFlag(IMenu::kPausesGame);
        --pUI->numPausesGame;
    }
}

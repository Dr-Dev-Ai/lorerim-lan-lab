#include <TiltedOnlinePCH.h>
#include <Services/SyncHealthService.h>
#include <Services/ImguiService.h>
#include <Services/TransportService.h>
#include <Services/CampaignService.h>
#include <Events/UpdateEvent.h>
#include <Events/ConnectedEvent.h>
#include <Events/DisconnectedEvent.h>
#include <Messages/ServerTimeSettings.h>
#include <World.h>
#include <Components.h>
#include <Interface/UI.h>
#include <TimeManager.h>
#include <BSGraphics/BSGraphicsRenderer.h>
#include <steam/isteamnetworkingutils.h>
#include <imgui.h>
#include <cmath>

double SyncHealthService::Now() noexcept
{
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

SyncHealthService::SyncHealthService(World& aWorld, entt::dispatcher& aDispatcher, TransportService& aTransport, ImguiService& aImgui)
    : m_world(aWorld), m_transport(aTransport)
{
    constexpr auto cIni = L".\\Data\\SKSE\\Plugins\\LoreRimSyncHealth.ini";
    m_mode = std::clamp(static_cast<int>(GetPrivateProfileIntW(L"Display", L"Mode", 1, cIni)), 0, 2);
    m_toggleKey = std::clamp(static_cast<int>(GetPrivateProfileIntW(L"Display", L"ToggleKey", VK_F10, cIni)), 1, 254);
    m_x = static_cast<int>(GetPrivateProfileIntW(L"Display", L"X", 24, cIni));
    m_y = static_cast<int>(GetPrivateProfileIntW(L"Display", L"Y", 150, cIni));
    m_fontScale = std::clamp(static_cast<int>(GetPrivateProfileIntW(L"Display", L"ScalePercent", 125, cIni)), 75, 200) / 100.f;
    m_update = aDispatcher.sink<UpdateEvent>().connect<&SyncHealthService::OnUpdate>(this);
    m_connected = aDispatcher.sink<ConnectedEvent>().connect<&SyncHealthService::OnConnected>(this);
    m_disconnected = aDispatcher.sink<DisconnectedEvent>().connect<&SyncHealthService::OnDisconnected>(this);
    m_time = aDispatcher.sink<ServerTimeSettings>().connect<&SyncHealthService::OnTime>(this);
    m_draw = aImgui.OnDraw.connect<&SyncHealthService::OnDraw>(this);
    spdlog::info("Sync Health: read-only panel ready; F10 cycles compact/details/off (configurable)");
}

void SyncHealthService::OnConnected(const ConnectedEvent&) noexcept
{
    m_connectedAt = Now();
    m_stalls = 0;
    m_loadedOnline = false;
    m_nextSample = m_nextHistory = 0.;
    std::lock_guard lock(m_mutex);
    m_snapshot = {};
    m_historyCount = m_historyNext = 0;
    m_pingHistory.fill(0.f);
    m_ageHistory.fill(0.f);
}

void SyncHealthService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    m_reportAt = m_reportNetworkAt = 0.;
    std::lock_guard lock(m_mutex);
    m_snapshot = {};
    // Keep the reason visible after the load guard closes the transport.
    m_snapshot.LoadedOnline = m_loadedOnline;
}

void SyncHealthService::NoteConnectedLoad() noexcept
{
    if (!m_transport.IsConnected())
        return;
    m_loadedOnline = true;
    spdlog::warn("Sync Health: loaded a save while connected; state agreement is unverified. Disconnect before loading, then reconnect to the agreed save.");
}

void SyncHealthService::OnTime(const ServerTimeSettings& aMessage) noexcept
{
    m_serverTime = aMessage.timeModel;
    m_reportAt = Now();
    m_reportNetworkAt = m_transport.GetMessageReceiveTime();
}

void SyncHealthService::OnUpdate(const UpdateEvent& aEvent) noexcept
{
    const double cNow = Now();
    m_lastUpdateAt.store(cNow, std::memory_order_relaxed);
    if (!m_transport.IsOnline() || !m_transport.IsConnected())
        return;
    if (cNow - m_connectedAt > 5000. && aEvent.Delta > 0.25)
        ++m_stalls;
    if (cNow < m_nextSample)
        return;
    m_nextSample = cNow + 200.;
    const double cNetworkNow = static_cast<double>(SteamNetworkingUtils()->GetLocalTimestamp()) / 1000.;
    const auto cStatus = m_transport.GetConnectionStatus();
    Snapshot sample;
    sample.Connected = true;
    sample.SampledAt = cNow;
    sample.LoadedOnline = m_loadedOnline;
    sample.Checkpoint = CampaignService::IsCheckpointActive();
    if (const auto* pUI = UI::Get())
        sample.Paused = pUI->numPausesGame != 0;
    sample.Ping = cStatus.m_nPing;
    sample.QualityIn = cStatus.m_flConnectionQualityLocal;
    sample.QualityOut = cStatus.m_flConnectionQualityRemote;
    sample.InKB = cStatus.m_flInBytesPerSec / 1024.f;
    sample.OutKB = cStatus.m_flOutBytesPerSec / 1024.f;
    sample.PendingBytes = cStatus.m_cbPendingReliable + cStatus.m_cbSentUnackedReliable;
    sample.QueueMs = static_cast<double>(cStatus.m_usecQueueTime) / 1000.;
    sample.PollAge = std::max(0., cNetworkNow - m_transport.GetLastPollTime());
    sample.FrameMs = aEvent.Delta * 1000.;
    sample.Stalls = m_stalls;
    sample.LocalActors = static_cast<uint32_t>(m_world.view<LocalComponent>().size());
    if (m_reportAt > 0.)
    {
        sample.ServerReportAge = std::max(0., cNow - m_reportAt);
        auto* pTime = TimeData::Get();
        if (pTime && pTime->GameHour && cNow - m_connectedAt > 5000.)
        {
            const double cElapsedMs = std::max(0., cNetworkNow - m_reportNetworkAt) + std::max(sample.Ping, 0) * 0.5;
            const double cExpectedHour = m_serverTime.Time + cElapsedMs * m_serverTime.TimeScale / 3600000.;
            sample.ClockErrorSeconds = std::remainder(pTime->GameHour->f - cExpectedHour, 24.) * 3600.;
            sample.ClockReady = std::isfinite(sample.ClockErrorSeconds);
        }
    }
    auto view = m_world.view<RemoteComponent, InterpolationComponent, FormIdComponent>();
    for (const auto entity : view)
    {
        const auto& interpolation = view.get<InterpolationComponent>(entity);
        if (!interpolation.Clock.IsRunning() || interpolation.LastSnapshotArrivalMs <= 0.)
            continue;
        ActorSample actor;
        actor.Form = view.get<FormIdComponent>(entity).Id;
        actor.Server = view.get<RemoteComponent>(entity).Id;
        actor.Age = std::max(0., cNetworkNow - interpolation.LastSnapshotArrivalMs);
        actor.Jitter = interpolation.Clock.GetJitter();
        actor.Delay = interpolation.Clock.GetTargetDelay();
        actor.Extrapolating = interpolation.IsExtrapolating;
        ++sample.RemoteActors;
        sample.Extrapolating += actor.Extrapolating ? 1 : 0;
        sample.StaleActors += actor.Age > std::max(1000., interpolation.Clock.GetSnapshotInterval() * 6.) ? 1 : 0;
        sample.Corrections += interpolation.CorrectionCount;
        sample.Snaps += interpolation.SnapCount;
        sample.LargestCorrection = std::max(sample.LargestCorrection, interpolation.LargestCorrection);
        // Keep only five oldest streams; no per-frame heap growth or game calls.
        size_t row = 0;
        while (row < sample.ActorRows && sample.Actors[row].Age >= actor.Age)
            ++row;
        if (row < sample.Actors.size())
        {
            for (size_t i = std::min(sample.ActorRows, sample.Actors.size() - 1); i > row; --i)
                sample.Actors[i] = sample.Actors[i - 1];
            sample.Actors[row] = actor;
            sample.ActorRows = std::min(sample.ActorRows + 1, sample.Actors.size());
        }
    }
    std::lock_guard lock(m_mutex);
    m_snapshot = sample;
    if (cNow >= m_nextHistory && sample.Ping >= 0)
    {
        m_nextHistory = cNow + 1000.;
        m_pingHistory[m_historyNext] = static_cast<float>(std::max(sample.Ping, 0));
        m_ageHistory[m_historyNext] = sample.ActorRows ? static_cast<float>(sample.Actors[0].Age) : 0.f;
        m_historyNext = (m_historyNext + 1) % m_pingHistory.size();
        m_historyCount = std::min(m_historyCount + 1, m_pingHistory.size());
    }
}

void SyncHealthService::OnDraw() noexcept
{
    if (auto* pWindow = BSGraphics::GetMainWindow(); pWindow && pWindow->IsForeground())
    {
        const bool cDown = (GetAsyncKeyState(m_toggleKey) & 0x8000) != 0;
        if (cDown && !m_keyDown)
            m_mode = (m_mode + 1) % 3;
        m_keyDown = cDown;
    }
    else
        m_keyDown = false;
    Snapshot sample;
    std::array<float, 120> ping{}, age{};
    size_t count{}, next{};
    {
        std::lock_guard lock(m_mutex);
        sample = m_snapshot;
        ping = m_pingHistory;
        age = m_ageHistory;
        count = m_historyCount;
        next = m_historyNext;
    }
    const bool cLoadDisconnect = !sample.Connected && sample.LoadedOnline;
    if ((!sample.Connected && !cLoadDisconnect) || (m_mode == 0 && !cLoadDisconnect))
        return;
    const double cUpdateAge = std::max(0., Now() - m_lastUpdateAt.load(std::memory_order_relaxed));
    const bool cWarning = sample.LoadedOnline || cUpdateAge > 750. || sample.Paused || sample.StaleActors
        || sample.Ping > 150 || (sample.QualityIn >= 0.f && sample.QualityIn < 0.98f)
        || (sample.QualityOut >= 0.f && sample.QualityOut < 0.98f) || sample.QueueMs > 100.
        || (sample.ClockReady && std::abs(sample.ClockErrorSeconds) > 60.);
    ImGui::SetNextWindowPos(ImVec2(static_cast<float>(m_x), static_cast<float>(m_y)), ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.82f);
    constexpr ImGuiWindowFlags cFlags = ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs
        | ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav
        | ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoTitleBar;
    if (ImGui::Begin("Sync Health", nullptr, cFlags))
    {
        ImGui::SetWindowFontScale(m_fontScale);
        if (cLoadDisconnect)
        {
            ImGui::TextColored(ImVec4(1.f, 0.75f, 0.25f, 1.f), "DISCONNECTED AFTER LOADING A SAVE");
            ImGui::TextUnformatted("Loading your save does not rewind the server or other players.");
            ImGui::TextUnformatted("Reconnect only with a save matching your party's progress.");
            ImGui::End();
            return;
        }
        ImGui::TextColored(cWarning ? ImVec4(1.f, 0.75f, 0.25f, 1.f) : ImVec4(0.4f, 0.9f, 0.65f, 1.f),
            "SYNC HEALTH  |  %s", cWarning ? "CHECK DETAILS" : "MONITORING");
        ImGui::TextDisabled("F10: compact / details / off");
        if (sample.LoadedOnline)
        {
            ImGui::TextColored(ImVec4(1.f, 0.75f, 0.25f, 1.f), "Save loaded while connected");
            ImGui::TextUnformatted("Disconnect, load the agreed save, reconnect.");
        }
        if (cUpdateAge > 750.)
            ImGui::Text("Client update gap: %.0f ms (pause/load/stall)", cUpdateAge);
        else if (sample.Checkpoint)
            ImGui::TextUnformatted("Paired checkpoint pause (expected)");
        else if (sample.Paused)
            ImGui::TextUnformatted("Game pause detected (rest/load may be expected)");
        if (sample.Ping >= 0)
            ImGui::Text("Ping: %d ms   Queue: %.1f ms", sample.Ping, sample.QueueMs);
        else
            ImGui::TextUnformatted("Ping / queue: waiting for measurements");
        if (sample.QualityIn >= 0.f && sample.QualityOut >= 0.f)
            ImGui::Text("Quality in/out: %.1f%% / %.1f%%", sample.QualityIn * 100.f, sample.QualityOut * 100.f);
        else
            ImGui::TextUnformatted("Connection quality: waiting for measurements");
        ImGui::Text("Actor streams: %u   Stale: %u   Predicting: %u", sample.RemoteActors, sample.StaleActors, sample.Extrapolating);
        if (sample.ClockReady)
            ImGui::Text("Time of day estimate: %+.1f game seconds", sample.ClockErrorSeconds);
        else
            ImGui::TextUnformatted("Time of day estimate: waiting / settling");
        ImGui::TextDisabled("Timing only; matching game state is not verified.");
        if (m_mode == 2)
        {
            ImGui::Separator();
            ImGui::Text("Traffic in/out: %.1f / %.1f KiB/s", sample.InKB, sample.OutKB);
            ImGui::Text("Reliable pending/unacked: %d bytes", sample.PendingBytes);
            ImGui::Text("Locally owned actors: %u", sample.LocalActors);
            ImGui::Text("Client update: %.1f ms   Poll age: %.1f ms", sample.FrameMs, sample.PollAge);
            ImGui::Text("Update gaps >250 ms this connection: %llu", static_cast<unsigned long long>(sample.Stalls));
            ImGui::Text("Loaded actor corrections/snaps: %llu / %llu", static_cast<unsigned long long>(sample.Corrections), static_cast<unsigned long long>(sample.Snaps));
            ImGui::Text("Largest correction: %.1f game units", sample.LargestCorrection);
            if (sample.ServerReportAge >= 0.)
                ImGui::Text("World-time report age: %.1f s", sample.ServerReportAge / 1000.);
            ImGui::TextDisabled("Server processing time: not reported");
            ImGui::TextDisabled("Quest / inventory agreement: not measured");
            ImGui::TextDisabled("Timing indicators do not prove matching game state.");
            if (count)
            {
                const int cOffset = count == ping.size() ? static_cast<int>(next) : 0;
                ImGui::PlotLines("Ping ms", ping.data(), static_cast<int>(count), cOffset, nullptr, 0.f, FLT_MAX, ImVec2(360.f, 45.f));
                ImGui::PlotLines("Oldest actor ms", age.data(), static_cast<int>(count), cOffset, nullptr, 0.f, FLT_MAX, ImVec2(360.f, 45.f));
            }
            ImGui::TextUnformatted("Oldest actor streams (form / age / jitter / buffer)");
            if (!sample.ActorRows)
                ImGui::TextDisabled("No remote actor samples yet (normal when alone)");
            for (size_t i = 0; i < sample.ActorRows; ++i)
            {
                const auto& actor = sample.Actors[i];
                ImGui::Text("%08X  %.0f / %.0f / %.0f ms%s", actor.Form, actor.Age, actor.Jitter, actor.Delay, actor.Extrapolating ? " predicting" : "");
            }
        }
    }
    ImGui::End();
}

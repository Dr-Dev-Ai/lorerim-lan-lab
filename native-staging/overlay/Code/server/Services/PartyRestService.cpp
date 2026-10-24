#include <Services/PartyRestService.h>
#include <World.h>
#include <GameServer.h>
#include <Events/UpdateEvent.h>
#include <Messages/PartyRestRequest.h>
#include <Messages/NotifyPartyRest.h>
#include <cmath>

PartyRestService::PartyRestService(World& aWorld, entt::dispatcher& aDispatcher) : m_world(aWorld)
{
    m_requestConnection = aDispatcher.sink<PacketEvent<PartyRestRequest>>().connect<&PartyRestService::OnRequest>(this);
    m_updateConnection = aDispatcher.sink<UpdateEvent>().connect<&PartyRestService::OnUpdate>(this);
}

bool PartyRestService::MembershipMatches(const Session& acSession) noexcept
{
    Player* pLeader = m_world.GetPlayerManager().GetById(acSession.Leader);
    const auto* pParty = pLeader ? m_world.GetPartyService().GetPlayerParty(pLeader) : nullptr;
    if (!pParty || pParty->LeaderPlayerId != acSession.Leader || pParty->Members.size() != acSession.Members.size())
        return false;
    for (Player* pPlayer : pParty->Members)
    {
        if (std::find(acSession.Members.begin(), acSession.Members.end(), pPlayer->GetId()) == acSession.Members.end())
            return false;
    }
    return true;
}

void PartyRestService::Broadcast(const Session& acSession, PartyRestAction aAction, bool aAdvance) noexcept
{
    NotifyPartyRest notify;
    notify.Session = acSession.Id;
    notify.Hours = acSession.Hours;
    notify.Action = aAction;
    notify.AdvanceTime = aAdvance;
    notify.Benefit = acSession.Benefit;
    for (uint32_t id : acSession.Members)
    {
        if (Player* pPlayer = m_world.GetPlayerManager().GetById(id))
            pPlayer->Send(notify);
    }
}

void PartyRestService::OnRequest(const PacketEvent<PartyRestRequest>& acEvent) noexcept
{
    const auto& request = acEvent.Packet;
    Player* pPlayer = acEvent.pPlayer;
    const auto* pParty = m_world.GetPartyService().GetPlayerParty(pPlayer);
    if (!pParty)
        return;
    const uint32_t cLeader = pParty->LeaderPlayerId;
    const uint64_t cNow = GameServer::Get()->GetTick();
    if (request.Action == PartyRestAction::Begin)
    {
        if (pPlayer->GetId() != cLeader || !std::isfinite(request.Hours) || request.Hours < 1.f || request.Hours > 24.f)
            return;
        if (m_sessions.find(cLeader) != m_sessions.end())
            return;
        Session session;
        session.Id = m_nextSession++;
        session.Leader = cLeader;
        session.Hours = request.Hours;
        session.Deadline = cNow + 120000;
        for (Player* pMember : pParty->Members)
            session.Members.push_back(pMember->GetId());
        m_sessions.emplace(cLeader, session);
        spdlog::info("[PartyRest] Begin session {}: {} hours, {} members", session.Id, session.Hours, session.Members.size());
        Broadcast(session, PartyRestAction::Begin);
        return;
    }
    const auto it = m_sessions.find(cLeader);
    if (it == m_sessions.end() || it->second.Id != request.Session)
        return;
    Session& session = it.value();
    if (!MembershipMatches(session) || cNow >= session.Deadline)
    {
        Broadcast(session, PartyRestAction::Cancel);
        m_sessions.erase(it);
        return;
    }
    switch (request.Action)
    {
    case PartyRestAction::Ready: session.ReadyAt[pPlayer->GetId()] = cNow; break;
    case PartyRestAction::Unsafe: session.ReadyAt.erase(pPlayer->GetId()); break;
    case PartyRestAction::Finish:
        if (pPlayer->GetId() == cLeader && !session.Finished && request.Benefit <= 3)
        {
            session.Finished = true;
            session.Benefit = request.Benefit;
            session.Deadline = cNow + 10000;
            // Require new safety acknowledgements after the sleeper wakes.
            session.ReadyAt.clear();
            spdlog::info("[PartyRest] Sleeper finished session {}; awaiting fresh safety reports", session.Id);
        }
        break;
    case PartyRestAction::Cancel:
        if (pPlayer->GetId() == cLeader)
        {
            Broadcast(session, PartyRestAction::Cancel);
            m_sessions.erase(it);
        }
        break;
    default: break;
    }
}

void PartyRestService::OnUpdate(const UpdateEvent&) noexcept
{
    const uint64_t cNow = GameServer::Get()->GetTick();
    for (auto it = m_sessions.begin(); it != m_sessions.end();)
    {
        Session& session = it.value();
        if (!MembershipMatches(session) || cNow >= session.Deadline)
        {
            Broadcast(session, PartyRestAction::Cancel);
            it = m_sessions.erase(it);
            continue;
        }
        bool ready = session.Finished;
        for (uint32_t id : session.Members)
        {
            const auto ack = session.ReadyAt.find(id);
            ready = ready && ack != session.ReadyAt.end() && cNow >= ack->second && cNow - ack->second <= 1500;
        }
        if (!ready)
        {
            ++it;
            continue;
        }
        // This LAN policy authorizes a world skip only when everybody connected
        // belongs to the resting party and has just acknowledged being safe.
        bool advance = true;
        for (Player* pPlayer : m_world.GetPlayerManager())
            advance = advance && std::find(session.Members.begin(), session.Members.end(), pPlayer->GetId()) != session.Members.end();
        if (advance)
            advance = m_world.GetCalendarService().AdvanceRestHours(session.Hours);
        // No benefits receipt unless the canonical clock actually advanced.
        spdlog::info("[PartyRest] Session {} clock advancement {}", session.Id, advance ? "accepted" : "rejected");
        Broadcast(session, advance ? PartyRestAction::Complete : PartyRestAction::Cancel, advance);
        it = m_sessions.erase(it);
    }
}

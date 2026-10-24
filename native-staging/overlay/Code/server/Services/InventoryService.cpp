#include <Services/CampaignService.h>
#include "InventoryService.h"

#include <Components.h>
#include <World.h>
#include <GameServer.h>

#include <Messages/NotifyObjectInventoryChanges.h>
#include <Messages/RequestInventoryChanges.h>
#include <Messages/NotifyInventoryChanges.h>
#include <Messages/RequestEquipmentChanges.h>
#include <Messages/NotifyEquipmentChanges.h>
#include <Messages/DrawWeaponRequest.h>

#include <Setting.h>
#include <DroppedItemClaim.h>
namespace
{
Console::Setting bEnableItemDrops{"Gameplay:bEnableItemDrops", "(Experimental) Syncs dropped items by players", false};
}

InventoryService::InventoryService(World& aWorld, entt::dispatcher& aDispatcher)
    : m_world(aWorld)
{
    m_inventoryChangeConnection = aDispatcher.sink<PacketEvent<RequestInventoryChanges>>().connect<&InventoryService::OnInventoryChanges>(this);
    m_equipmentChangeConnection = aDispatcher.sink<PacketEvent<RequestEquipmentChanges>>().connect<&InventoryService::OnEquipmentChanges>(this);
    m_drawWeaponConnection = aDispatcher.sink<PacketEvent<DrawWeaponRequest>>().connect<&InventoryService::OnWeaponDrawnRequest>(this);
}

void InventoryService::OnInventoryChanges(const PacketEvent<RequestInventoryChanges>& acMessage) noexcept
{
    auto& message = acMessage.Packet;
    const auto rejectClaim = [&]()
    {
        if (message.DroppedId && message.ClaimId)
        {
            NotifyInventoryChanges denied;
            denied.ServerId = message.ServerId;
            denied.OwnershipEpoch = message.OwnershipEpoch;
            denied.DroppedId = message.DroppedId;
            denied.ClaimId = message.ClaimId;
            acMessage.pPlayer->Send(denied);
        }
    };

    auto view = m_world.view<InventoryComponent>();

    const auto it = view.find(static_cast<entt::entity>(message.ServerId));

    if (it == view.end())
    {
        rejectClaim();
        return;
    }

    bool isRemoteNpcInteraction = false;

    const auto* pOwnerComponent = m_world.try_get<OwnerComponent>(*it);
    if (pOwnerComponent)
    {
        const auto* pOwner = pOwnerComponent->GetOwner();
        if (pOwnerComponent->OwnershipEpoch != message.OwnershipEpoch)
        {
            const uint32_t ownerId = pOwner ? pOwner->GetId() : 0;
            spdlog::debug(
                "Rejected inventory change from player {:X} for actor {:X} at stale epoch {}; current owner is {:X} at epoch {}",
                acMessage.pPlayer->GetId(), message.ServerId, message.OwnershipEpoch, ownerId, pOwnerComponent->OwnershipEpoch);
            rejectClaim();
            return;
        }

        if (pOwner != acMessage.pPlayer)
        {
            const auto* pCharacterComponent = m_world.try_get<CharacterComponent>(*it);
            const auto* pCellComponent = m_world.try_get<CellIdComponent>(*it);
            // A non-owner may still change an NPC's inventory through normal gameplay interactions
            // such as pickpocketing or looting. The epoch and range checks keep the interaction tied
            // to the currently visible incarnation of that NPC.
            isRemoteNpcInteraction = pOwner && pCharacterComponent && pCellComponent && !pCharacterComponent->IsPlayer()
                && acMessage.pPlayer->GetCellComponent().IsInRange(*pCellComponent, pCharacterComponent->IsDragon());

            if (isRemoteNpcInteraction && CampaignService::IsRequired())
            {
                const auto* reference = m_world.try_get<FormIdComponent>(*it);
                isRemoteNpcInteraction = reference && m_world.ctx().at<CampaignService>().CanInteract(acMessage.pPlayer, reference->Id);
            }
            if (!isRemoteNpcInteraction)
            {
                const uint32_t ownerId = pOwner ? pOwner->GetId() : 0;
                spdlog::debug(
                    "Rejected inventory change from player {:X} for actor {:X} because it is owned by player {:X}", acMessage.pPlayer->GetId(), message.ServerId, ownerId);
                rejectClaim();
                return;
            }
        }
    }
    else if (message.OwnershipEpoch != 0)
    {
        spdlog::warn(
            "Rejected inventory change from player {:X} because object {:X} unexpectedly carried ownership epoch {}",
            acMessage.pPlayer->GetId(), message.ServerId, message.OwnershipEpoch);
        rejectClaim();
        return;
    }

    auto& inventoryComponent = view.get<InventoryComponent>(*it);
    Inventory::Entry transaction = message.Item;
    if (message.DroppedId && !message.Drop)
    {
        NotifyInventoryChanges denied;
        denied.ServerId = message.ServerId;
        denied.OwnershipEpoch = message.OwnershipEpoch;
        denied.DroppedId = message.DroppedId;
        denied.ClaimId = message.ClaimId;
        const uint32_t cClaim = static_cast<uint32_t>(message.ClaimId);
        const auto dropped = m_drops.find(message.DroppedId);
        const CellIdComponent dropCell = dropped != m_drops.end()
            ? CellIdComponent{dropped->second.Cell, dropped->second.WorldSpace, dropped->second.Coords} : CellIdComponent{};
        if (!message.ClaimId || static_cast<uint32_t>(message.ClaimId >> 32) != message.ServerId
            || cClaim <= m_lastClaim[message.ServerId] || dropped == m_drops.end()
            || isRemoteNpcInteraction || message.Item.Count <= 0 || message.Item.Count > dropped.value().Item.Count
            || !acMessage.pPlayer->GetCellComponent().IsInRange(dropCell, false))
        {
            acMessage.pPlayer->Send(denied);
            return;
        }
        m_lastClaim[message.ServerId] = cClaim;
        // Ignore client-supplied enchantment/temper metadata for a claimed item.
        transaction = dropped->second.Item;
        transaction.Count = message.Item.Count;
        if (!ConsumeDroppedCount(dropped.value().Item.Count, transaction.Count))
        {
            acMessage.pPlayer->Send(denied);
            return;
        }
        if (!dropped.value().Item.Count)
            m_drops.erase(dropped);
    }
    else if (message.Drop && message.DroppedId)
    {
        const uint32_t cSequence = static_cast<uint32_t>(message.DroppedId);
        if (static_cast<uint32_t>(message.DroppedId >> 32) != message.ServerId || !cSequence
            || cSequence <= m_lastDrop[message.ServerId] || message.Item.Count >= 0 || message.Item.Count == INT32_MIN
            || isRemoteNpcInteraction)
            return;
        m_lastDrop[message.ServerId] = cSequence;
        if (bEnableItemDrops)
        {
            DroppedItem dropped;
            dropped.Item = message.Item;
            dropped.Item.Count = -message.Item.Count;
            dropped.Item.ExtraWorn = dropped.Item.ExtraWornLeft = false;
            const auto& cell = acMessage.pPlayer->GetCellComponent();
            dropped.Cell = cell.Cell;
            dropped.WorldSpace = cell.WorldSpaceId;
            dropped.Coords = cell.CenterCoords;
            m_drops.emplace(message.DroppedId, std::move(dropped));
        }
    }
    if (transaction.Count != 0) m_world.ctx().at<CampaignService>().NoteWorldChange();
    inventoryComponent.Content.AddOrRemoveEntry(transaction);

    if (!message.UpdateClients && !isRemoteNpcInteraction && !message.ClaimId)
        return;

    NotifyInventoryChanges notify;
    notify.ServerId = message.ServerId;
    notify.OwnershipEpoch = message.OwnershipEpoch;
    notify.Item = transaction;
    notify.DroppedId = message.DroppedId;
    notify.ClaimId = message.ClaimId;

    notify.Drop = bEnableItemDrops && message.DroppedId && !isRemoteNpcInteraction ? message.Drop : false;

    if (message.ClaimId)
        acMessage.pPlayer->Send(notify);
    const entt::entity cOrigin = static_cast<entt::entity>(message.ServerId);
    if (!GameServer::Get()->SendToPlayersInRange(notify, cOrigin, acMessage.GetSender()))
        spdlog::error("{}: SendToPlayersInRange failed", __FUNCTION__);
}

void InventoryService::OnEquipmentChanges(const PacketEvent<RequestEquipmentChanges>& acMessage) noexcept
{
    auto& message = acMessage.Packet;
    auto view = m_world.view<InventoryComponent>();

    const auto it = view.find(static_cast<entt::entity>(message.ServerId));

    if (it == view.end())
        return;

    const auto* pOwnerComponent = m_world.try_get<OwnerComponent>(*it);
    if (pOwnerComponent)
    {
        if (pOwnerComponent->GetOwner() != acMessage.pPlayer || pOwnerComponent->OwnershipEpoch != message.OwnershipEpoch)
        {
            const uint32_t ownerId = pOwnerComponent->GetOwner() ? pOwnerComponent->GetOwner()->GetId() : 0;
            spdlog::debug(
                "Rejected equipment change from player {:X} for actor {:X}; current owner is {:X} and requested epoch {} does not match {}",
                acMessage.pPlayer->GetId(), message.ServerId, ownerId, message.OwnershipEpoch, pOwnerComponent->OwnershipEpoch);
            return;
        }
    }
    else if (message.OwnershipEpoch != 0)
    {
        spdlog::warn(
            "Rejected equipment change from player {:X} because object {:X} unexpectedly carried ownership epoch {}",
            acMessage.pPlayer->GetId(), message.ServerId, message.OwnershipEpoch);
        return;
    }

    auto& inventoryComponent = view.get<InventoryComponent>(*it);
    inventoryComponent.Content.UpdateEquipment(message.CurrentInventory);

    NotifyEquipmentChanges notify;
    notify.ServerId = message.ServerId;
    notify.OwnershipEpoch = message.OwnershipEpoch;
    notify.ItemId = message.ItemId;
    notify.EquipSlotId = message.EquipSlotId;
    notify.Count = message.Count;
    notify.Unequip = message.Unequip;
    notify.IsSpell = message.IsSpell;
    notify.IsShout = message.IsShout;

    const entt::entity cOrigin = static_cast<entt::entity>(message.ServerId);
    if (!GameServer::Get()->SendToPlayersInRange(notify, cOrigin, acMessage.GetSender()))
        spdlog::error("{}: SendToPlayersInRange failed", __FUNCTION__);
}

void InventoryService::OnWeaponDrawnRequest(const PacketEvent<DrawWeaponRequest>& acMessage) noexcept
{
    auto& message = acMessage.Packet;

    auto characterView = m_world.view<CharacterComponent, OwnerComponent>();
    const auto it = characterView.find(static_cast<entt::entity>(message.Id));

    if (it != std::end(characterView) && characterView.get<OwnerComponent>(*it).GetOwner() == acMessage.pPlayer)
    {
        auto& characterComponent = characterView.get<CharacterComponent>(*it);
        characterComponent.SetWeaponDrawn(message.IsWeaponDrawn);
        spdlog::debug("Updating weapon drawn state {:x}:{}", message.Id, message.IsWeaponDrawn);
    }
}

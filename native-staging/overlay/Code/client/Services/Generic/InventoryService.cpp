#include <Services/InventoryService.h>

#include <Messages/RequestObjectInventoryChanges.h>
#include <Messages/NotifyObjectInventoryChanges.h>
#include <Messages/RequestInventoryChanges.h>
#include <Messages/NotifyInventoryChanges.h>
#include <Messages/RequestEquipmentChanges.h>
#include <Messages/NotifyEquipmentChanges.h>
#include <Messages/DrawWeaponRequest.h>
#include <Messages/NotifyDrawWeapon.h>

#include <Events/UpdateEvent.h>
#include <Events/DisconnectedEvent.h>
#include <Events/DroppedItemPickupEvent.h>
#include <Events/InventoryChangeEvent.h>
#include <Events/EquipmentChangeEvent.h>

#include <World.h>
#include <Games/Skyrim/Interface/UI.h>
#include <PlayerCharacter.h>
#include <Forms/TESObjectCELL.h>
#include <Actor.h>
#include <Structs/ObjectData.h>
#include <Forms/TESWorldSpace.h>
#include <Games/TES.h>
#include <Games/Overrides.h>
#include <EquipManager.h>
#include <Games/ActorExtension.h>
#include <Forms/TESNPC.h>
#include <DefaultObjectManager.h>

InventoryService::InventoryService(World& aWorld, entt::dispatcher& aDispatcher, TransportService& aTransport) noexcept
    : m_world(aWorld)
    , m_dispatcher(aDispatcher)
    , m_transport(aTransport)
{
    m_pickupConnection = m_dispatcher.sink<DroppedItemPickupEvent>().connect<&InventoryService::OnPickupDropped>(this);
    m_disconnectConnection = m_dispatcher.sink<DisconnectedEvent>().connect<&InventoryService::OnDisconnected>(this);
    m_updateConnection = m_dispatcher.sink<UpdateEvent>().connect<&InventoryService::OnUpdate>(this);
    m_inventoryConnection = m_dispatcher.sink<InventoryChangeEvent>().connect<&InventoryService::OnInventoryChangeEvent>(this);
    m_equipmentConnection = m_dispatcher.sink<EquipmentChangeEvent>().connect<&InventoryService::OnEquipmentChangeEvent>(this);
    m_inventoryChangeConnection = m_dispatcher.sink<NotifyInventoryChanges>().connect<&InventoryService::OnNotifyInventoryChanges>(this);
    m_equipmentChangeConnection = m_dispatcher.sink<NotifyEquipmentChanges>().connect<&InventoryService::OnNotifyEquipmentChanges>(this);
}

void InventoryService::OnUpdate(const UpdateEvent& acUpdateEvent) noexcept
{
    RunWeaponStateUpdates();
    if (m_transport.IsConnected() && m_world.GetTick() >= m_nextClaimRetry)
    {
        m_nextClaimRetry = m_world.GetTick() + 500;
        Vector<NotifyInventoryChanges> pending;
        pending.swap(m_pendingClaims);
        for (const auto& message : pending)
            OnNotifyInventoryChanges(message);
    }
}

void InventoryService::OnInventoryChangeEvent(const InventoryChangeEvent& acEvent) noexcept
{
    if (!m_transport.IsConnected())
        return;

    auto view = m_world.view<FormIdComponent>();

    const auto iter = std::find_if(std::begin(view), std::end(view), [view, formId = acEvent.FormId](auto entity) { return view.get<FormIdComponent>(entity).Id == formId; });

    if (iter == std::end(view))
        return;

    uint32_t serverId = 0;
    if (acEvent.OwnershipEpoch != 0)
    {
        const auto* pLocalComponent = m_world.try_get<LocalComponent>(*iter);
        const auto* pRemoteComponent = m_world.try_get<RemoteComponent>(*iter);
        const bool ownershipMatches = (pLocalComponent && pLocalComponent->Id == acEvent.ServerId && pLocalComponent->OwnershipEpoch == acEvent.OwnershipEpoch)
            || (pRemoteComponent && pRemoteComponent->Id == acEvent.ServerId && pRemoteComponent->OwnershipEpoch == acEvent.OwnershipEpoch);

        if (!ownershipMatches)
        {
            spdlog::debug("Discarded an inventory change for actor {:X} because ownership changed after it was queued (epoch {})", acEvent.ServerId, acEvent.OwnershipEpoch);
            return;
        }

        serverId = acEvent.ServerId;
    }
    else
    {
        if (Cast<Actor>(TESForm::GetById(acEvent.FormId)))
            return;

        const std::optional<uint32_t> serverIdRes = Utils::GetServerId(*iter);
        if (!serverIdRes)
        {
            spdlog::warn(
                "Discarded inventory change for form {:X} because it has no server entity (item {:X}, count {})", acEvent.FormId, acEvent.Item.BaseId.BaseId, acEvent.Item.Count);
            return;
        }
        serverId = *serverIdRes;
    }

    RequestInventoryChanges request;
    request.ServerId = serverId;
    request.OwnershipEpoch = acEvent.OwnershipEpoch;
    request.Item = acEvent.Item;
    request.Drop = acEvent.Drop;
    request.DroppedId = acEvent.DroppedId;
    request.UpdateClients = acEvent.UpdateClients;

    m_transport.Send(request);

    spdlog::info("Sending item request, item: {:X}, count: {}, target object: {:X}", acEvent.Item.BaseId.BaseId, acEvent.Item.Count, acEvent.FormId);
}

void InventoryService::OnEquipmentChangeEvent(const EquipmentChangeEvent& acEvent) noexcept
{
    if (!m_transport.IsConnected())
        return;

    auto view = m_world.view<FormIdComponent>();

    const auto iter = std::find_if(std::begin(view), std::end(view), [view, formId = acEvent.ActorId](auto entity) { return view.get<FormIdComponent>(entity).Id == formId; });

    if (iter == std::end(view))
        return;

    const auto* pLocalComponent = m_world.try_get<LocalComponent>(*iter);
    if (acEvent.OwnershipEpoch == 0 || !pLocalComponent || pLocalComponent->Id != acEvent.ServerId || pLocalComponent->OwnershipEpoch != acEvent.OwnershipEpoch)
    {
        spdlog::debug("Discarded an equipment change for actor {:X} because ownership changed after it was queued (epoch {})", acEvent.ServerId, acEvent.OwnershipEpoch);
        return;
    }

    Actor* pActor = Cast<Actor>(TESForm::GetById(acEvent.ActorId));
    if (!pActor)
        return;

    auto& modSystem = World::Get().GetModSystem();

    RequestEquipmentChanges request;
    request.ServerId = acEvent.ServerId;
    request.OwnershipEpoch = acEvent.OwnershipEpoch;

    if (!modSystem.GetServerModId(acEvent.EquipSlotId, request.EquipSlotId))
        return;
    if (!modSystem.GetServerModId(acEvent.ItemId, request.ItemId))
        return;

    request.Count = acEvent.Count;
    request.Unequip = acEvent.Unequip;
    request.IsSpell = acEvent.IsSpell;
    request.IsShout = acEvent.IsShout;
    request.IsAmmo = acEvent.IsAmmo;
    request.CurrentInventory = pActor->GetEquipment();

    m_transport.Send(request);

    spdlog::info("Sending equipment request, item: {:X}, count: {}, target object: {:X}", acEvent.ItemId, acEvent.Count, acEvent.ActorId);
}

void InventoryService::OnNotifyInventoryChanges(const NotifyInventoryChanges& acMessage) noexcept
{
    if (acMessage.DroppedId && !acMessage.Drop)
    {
        // A claim result is the only path that may credit a tracked dropped item.
        uint32_t formId = 0;
        {
            std::lock_guard lock(m_dropMutex);
            const auto it = m_drops.find(acMessage.DroppedId);
            if (it == m_drops.end())
                return;
            it.value().Pending = false;
            if (!acMessage.ClaimId || acMessage.Item.Count <= 0)
                return;
            const uint32_t cPicker = static_cast<uint32_t>(acMessage.ClaimId >> 32);
            if (cPicker != acMessage.ServerId || m_appliedClaims.contains(acMessage.ClaimId))
                return;
            formId = it.value().FormId;
        }
        Actor* pPicker = Utils::GetByServerId<Actor>(acMessage.ServerId);
        TESObjectREFR* pObject = Cast<TESObjectREFR>(TESForm::GetById(formId));
        if (!pPicker || !pObject)
        {
            spdlog::debug("Deferring dropped-item claim {} until its picker/reference loads", acMessage.ClaimId);
            m_pendingClaims.push_back(acMessage);
            return;
        }
        {
            ScopedInventoryOverride _;
            ScopedActivateOverride activation;
            pPicker->PickUpObject(pObject, acMessage.Item.Count, false, 0.f);
        }
        std::lock_guard lock(m_dropMutex);
        m_appliedClaims.insert(acMessage.ClaimId);
        const auto it = m_drops.find(acMessage.DroppedId);
        if (it != m_drops.end())
        {
            it.value().Item.Count -= acMessage.Item.Count;
            if (it.value().Item.Count <= 0)
                m_drops.erase(it);
        }
        return;
    }
    if (acMessage.OwnershipEpoch != 0)
    {
        Actor* pActor = nullptr;

        auto remoteView = m_world.view<RemoteComponent, FormIdComponent>(entt::exclude<LocalComponent>);
        const auto remoteIt = std::find_if(remoteView.begin(), remoteView.end(), [remoteView, &acMessage](const entt::entity aEntity)
        {
            const auto& remoteComponent = remoteView.get<RemoteComponent>(aEntity);
            return remoteComponent.Id == acMessage.ServerId && remoteComponent.OwnershipEpoch == acMessage.OwnershipEpoch;
        });

        if (remoteIt != remoteView.end())
            pActor = Cast<Actor>(TESForm::GetById(remoteView.get<FormIdComponent>(*remoteIt).Id));
        else
        {
            auto localView = m_world.view<LocalComponent, FormIdComponent>();
            const auto localIt = std::find_if(localView.begin(), localView.end(), [localView, &acMessage](const entt::entity aEntity)
            {
                const auto& localComponent = localView.get<LocalComponent>(aEntity);
                return localComponent.Id == acMessage.ServerId && localComponent.OwnershipEpoch == acMessage.OwnershipEpoch;
            });

            if (localIt != localView.end())
                pActor = Cast<Actor>(TESForm::GetById(localView.get<FormIdComponent>(*localIt).Id));
        }

        if (!pActor)
        {
            spdlog::debug("Discarded an inventory update for actor {:X} because epoch {} is no longer current", acMessage.ServerId, acMessage.OwnershipEpoch);
            return;
        }

        ScopedInventoryOverride _;

        if (acMessage.Drop)
        {
            TESObjectREFR* pDropped = pActor->DropOrPickUpObject(acMessage.Item, nullptr, nullptr);
            if (pDropped && acMessage.DroppedId)
            {
                DroppedReference dropped;
                dropped.Id = acMessage.DroppedId;
                dropped.FormId = pDropped->formID;
                dropped.Replica = true;
                dropped.Item = acMessage.Item;
                dropped.Item.Count = -acMessage.Item.Count;
                dropped.Item.ExtraWorn = dropped.Item.ExtraWornLeft = false;
                std::lock_guard lock(m_dropMutex);
                m_drops.emplace(dropped.Id, std::move(dropped));
            }
        }
        else
            pActor->AddOrRemoveItem(acMessage.Item);

        return;
    }

    TESObjectREFR* pObject = Utils::GetByServerId<TESObjectREFR>(acMessage.ServerId);
    if (!pObject)
        return;

    ScopedInventoryOverride _;
    pObject->AddOrRemoveItem(acMessage.Item);
}

void InventoryService::OnNotifyEquipmentChanges(const NotifyEquipmentChanges& acMessage) noexcept
{
    auto view = m_world.view<RemoteComponent, FormIdComponent>(entt::exclude<LocalComponent>);
    const auto it = std::find_if(view.begin(), view.end(), [view, &acMessage](const entt::entity aEntity)
    {
        const auto& remoteComponent = view.get<RemoteComponent>(aEntity);
        return remoteComponent.Id == acMessage.ServerId && remoteComponent.OwnershipEpoch == acMessage.OwnershipEpoch;
    });
    if (it == view.end())
    {
        spdlog::debug("Discarded an equipment update for actor {:X} because epoch {} is no longer current", acMessage.ServerId, acMessage.OwnershipEpoch);
        return;
    }

    Actor* pActor = Cast<Actor>(TESForm::GetById(view.get<FormIdComponent>(*it).Id));
    if (!pActor)
        return;

    auto& modSystem = World::Get().GetModSystem();

    uint32_t itemId = modSystem.GetGameId(acMessage.ItemId);
    TESForm* pItem = TESForm::GetById(itemId);

    if (!pItem)
    {
        spdlog::error("Could not find inventory item {:X}:{:X}", acMessage.ItemId.ModId, acMessage.ItemId.BaseId);
        return;
    }

    uint32_t equipSlotId = modSystem.GetGameId(acMessage.EquipSlotId);
    TESForm* pEquipSlot = TESForm::GetById(equipSlotId);

    uint32_t slotId = 0;
    if (pEquipSlot == DefaultObjectManager::Get().rightEquipSlot)
        slotId = 1;

    auto* pEquipManager = EquipManager::Get();

    if (acMessage.IsSpell)
    {
        if (acMessage.Unequip)
            pEquipManager->UnEquipSpell(pActor, pItem, slotId);
        else
            pEquipManager->EquipSpell(pActor, pItem, slotId);

        return;
    }
    else if (acMessage.IsShout)
    {
        if (acMessage.Unequip)
            pEquipManager->UnEquipShout(pActor, pItem);
        else
            pEquipManager->EquipShout(pActor, pItem);

        return;
    }

    // TODO: ExtraData necessary? probably
    if (acMessage.Unequip)
    {
        pEquipManager->UnEquip(pActor, pItem, nullptr, acMessage.Count, pEquipSlot, false, true, false, false, nullptr);
    }
    else
    {
        // Unequip all armor first, since the game won't auto unequip armor
        Inventory wornArmor{};
        if (pItem->formType == FormType::Armor)
        {
            wornArmor = pActor->GetWornArmor();
            for (const auto& armor : wornArmor.Entries)
            {
                uint32_t armorId = modSystem.GetGameId(armor.BaseId);
                TESForm* pArmor = TESForm::GetById(armorId);
                if (pArmor)
                    pEquipManager->UnEquip(pActor, pArmor, nullptr, 1, pEquipSlot, false, true, false, false, nullptr);
            }
        }

        pEquipManager->Equip(pActor, pItem, nullptr, acMessage.Count, pEquipSlot, false, true, false, false);

        for (const auto& armor : wornArmor.Entries)
        {
            uint32_t armorId = modSystem.GetGameId(armor.BaseId);
            TESForm* pArmor = TESForm::GetById(armorId);
            if (pArmor)
                pEquipManager->Equip(pActor, pArmor, nullptr, 1, pEquipSlot, false, true, false, false);
        }
    }
}

void InventoryService::RunWeaponStateUpdates() noexcept
{
    if (!m_transport.IsConnected())
        return;

    static std::chrono::steady_clock::time_point lastSendTimePoint;
    constexpr auto cDelayBetweenUpdates = 500ms;

    const auto now = std::chrono::steady_clock::now();
    if (now - lastSendTimePoint < cDelayBetweenUpdates)
        return;

    lastSendTimePoint = now;

    auto view = m_world.view<FormIdComponent, LocalComponent>();

    for (auto entity : view)
    {
        const auto& formIdComponent = view.get<FormIdComponent>(entity);
        Actor* const pActor = Cast<Actor>(TESForm::GetById(formIdComponent.Id));
        auto& localComponent = view.get<LocalComponent>(entity);

        bool isWeaponDrawn = pActor->actorState.IsWeaponDrawn();
        if (isWeaponDrawn != localComponent.IsWeaponDrawn)
        {
            localComponent.IsWeaponDrawn = isWeaponDrawn;

            DrawWeaponRequest request;
            request.Id = localComponent.Id;
            request.IsWeaponDrawn = isWeaponDrawn;

            m_transport.Send(request);
        }
    }
}

bool InventoryService::TryPickupDropped(Actor* apActor, TESObjectREFR* apObject, int32_t aCount) noexcept
{
    if (!apObject || apActor != PlayerCharacter::Get())
        return false;
    uint64_t id = 0;
    {
        std::lock_guard lock(m_dropMutex);
        for (auto it = m_drops.begin(); it != m_drops.end(); ++it)
        {
            auto& reference = it.value();
            const uint64_t key = it.key();
            if (reference.FormId != apObject->formID)
                continue;
            if (reference.Pending || aCount <= 0 || aCount > reference.Item.Count)
                return true;
            reference.Pending = true;
            id = key;
            break;
        }
    }
    if (!id)
        return false;
    m_world.GetRunner().Trigger(DroppedItemPickupEvent{apActor->formID, id, aCount});
    return true;
}

void InventoryService::OnPickupDropped(const DroppedItemPickupEvent& acEvent) noexcept
{
    const auto ownership = Utils::GetLocalOwnershipToken(acEvent.ActorId);
    std::lock_guard lock(m_dropMutex);
    const auto it = m_drops.find(acEvent.DroppedId);
    if (it == m_drops.end())
        return;
    if (!m_transport.IsConnected() || !ownership || !m_nextClaim)
    {
        it.value().Pending = false;
        return;
    }
    RequestInventoryChanges request;
    request.ServerId = ownership->ServerId;
    request.OwnershipEpoch = ownership->OwnershipEpoch;
    request.DroppedId = acEvent.DroppedId;
    request.ClaimId = (uint64_t{request.ServerId} << 32) | m_nextClaim++;
    request.Item = it.value().Item;
    request.Item.Count = acEvent.Count;
    m_transport.Send(request);
}

void InventoryService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    std::lock_guard lock(m_dropMutex);
    // Remove only generated replicas; keep original local dropped items.
    // Do not let an old network ID be interpreted in the next session.
    for (const auto& [id, reference] : m_drops)
    {
        if (!reference.Replica)
            continue;
        if (TESObjectREFR* pObject = Cast<TESObjectREFR>(TESForm::GetById(reference.FormId)))
        {
            pObject->Disable();
            pObject->Delete();
        }
    }
    m_drops.clear();
    m_appliedClaims.clear();
    m_pendingClaims.clear();
    m_nextClaimRetry = 0;
    m_nextDrop = m_nextClaim = 1;
}

uint64_t InventoryService::RegisterDropped(Actor* apActor, TESObjectREFR* apDropped, const Inventory::Entry& acItem) noexcept
{
    const auto ownership = Utils::GetLocalOwnershipToken(apActor->formID);
    if (!ownership || !apDropped || acItem.Count >= 0 || acItem.Count == INT32_MIN)
        return 0;
    std::lock_guard lock(m_dropMutex);
    if (!m_nextDrop)
        return 0;
    DroppedReference reference;
    reference.Id = (uint64_t{ownership->ServerId} << 32) | m_nextDrop++;
    reference.FormId = apDropped->formID;
    reference.Item = acItem;
    reference.Item.Count = -acItem.Count;
    reference.Item.ExtraWorn = reference.Item.ExtraWornLeft = false;
    const uint64_t cId = reference.Id;
    m_drops.emplace(cId, std::move(reference));
    return cId;
}

bool InventoryService::HasPendingDropClaims() noexcept
{
    std::lock_guard lock(m_dropMutex);
    for (const auto& [id, drop] : m_drops) if (drop.Pending) return true;
    return false;
}

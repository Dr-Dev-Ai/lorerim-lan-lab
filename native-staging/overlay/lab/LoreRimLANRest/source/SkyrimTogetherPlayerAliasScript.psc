ScriptName SkyrimTogetherPlayerAliasScript extends ReferenceAlias

SkyrimTogetherVerifyLaunchScript Property VerifyLaunchScript Auto
Bool localSleep = False
Bool restSnapshotValid = False
Float restStartExhaustion = 0.0
Float restRestorePerHour = 0.0
Int campaignFollowerPoll = 0

Event OnInit()
    RegisterForSleep()
    RegisterForSingleUpdate(1.0)
EndEvent

Event OnPlayerLoadGame()
    VerifyLaunchScript.VerifyLaunch()
    RegisterForSleep()
    RegisterForSingleUpdate(1.0)
    localSleep = False
    restSnapshotValid = False
EndEvent

Event OnSleepStart(Float startTime, Float endTime)
    Float hours = (endTime - startTime) * 24.0
    If hours >= 0.99 && hours <= 24.01 && LoreRimLANRest.RestExchange(-3.0) > 0.0
        localSleep = True
        LoreRimLANRest.RestExchange(Math.Floor(hours + 0.01))
    EndIf
EndEvent

Event OnSleepStop(Bool interrupted)
    If localSleep
        If interrupted
            LoreRimLANRest.RestExchange(-2.0)
            localSleep = False
        Else
            LoreRimLANRest.RestExchange(-1.0)
        EndIf
    EndIf
EndEvent

Event OnUpdate()
    ; Ready is withheld until this player's own SMI need has been captured.
    ; These forms and the API were checked against installed SMI 1.5.2.
    GlobalVariable exhaustion = Game.GetFormFromFile(0x816, "ccQDRSSE001-SurvivalMode.esl") as GlobalVariable
    GlobalVariable restoreRate = Game.GetFormFromFile(0x80E, "ccQDRSSE001-SurvivalMode.esl") as GlobalVariable
    GlobalVariable exhaustionTimestamp = Game.GetFormFromFile(0xA16, "SurvivalModeImproved.esp") as GlobalVariable
    If LoreRimLANRest.RestExchange(-8.0) > 0.0
        If !restSnapshotValid && exhaustion && restoreRate && exhaustionTimestamp
            restStartExhaustion = exhaustion.GetValue()
            restRestorePerHour = restoreRate.GetValue()
            If restStartExhaustion >= 0.0 && restRestorePerHour >= 0.0
                restSnapshotValid = True
                LoreRimLANRest.RestExchange(-9.0)
            EndIf
        EndIf
    Else
        restSnapshotValid = False
    EndIf
    campaignFollowerPoll += 1
    If campaignFollowerPoll >= 5 && LoreRimLANRest.CampaignFollower(0, 6) == 1
        campaignFollowerPoll = 0
        DialogueFollowerScript campaignFollowers = Game.GetForm(0x000750BA) as DialogueFollowerScript
        If campaignFollowers
            campaignFollowers.LoreRimCampaignReportFollowers()
        EndIf
    EndIf
    Int managed = 0
    Int followerId = LoreRimLANRest.NextCampaignFollower()
    While followerId != 0 && managed < 8
        Actor campaignActor = Game.GetForm(followerId) as Actor
        Int policy = LoreRimLANRest.CampaignFollower(followerId, 9)
        If campaignActor && !campaignActor.IsDead() && policy > 0
            Float desiredWait = 1.0
            If policy == 2
                desiredWait = 0.0
            EndIf
            If campaignActor.GetAV("WaitingForPlayer") != desiredWait
                campaignActor.SetAV("WaitingForPlayer", desiredWait)
                campaignActor.EvaluatePackage()
            EndIf
        EndIf
        managed += 1
        followerId = LoreRimLANRest.NextCampaignFollower()
    EndWhile
    Int refreshed = 0
    Int actorId = LoreRimLANRest.NextEquipmentActor()
    While actorId != 0 && refreshed < 8
        Actor remote = Game.GetForm(actorId) as Actor
        If remote && SkyrimTogetherUtils.IsRemotePlayer(remote)
            IED.Reset(remote)
        EndIf
        refreshed += 1
        actorId = LoreRimLANRest.NextEquipmentActor()
    EndWhile
    Actor player = Game.GetPlayer()
    If player && !player.IsDead() && !player.IsInCombat() && !Utility.IsInMenuMode()
        Float hours = LoreRimLANRest.RestExchange(0.0)
        If hours > 0.0 && restSnapshotValid && exhaustion && exhaustionTimestamp
            Float targetExhaustion = restStartExhaustion - hours * restRestorePerHour
            If targetExhaustion < 0.0
                targetExhaustion = 0.0
            EndIf
            Float remainingRelief = exhaustion.GetValue() - targetExhaustion
            If remainingRelief < 0.0
                remainingRelief = 0.0
            EndIf
            ; Mirror SMI's normal wake timestamp before its public restore API.
            ; The API also reconciles stage spells, tracked magicka penalties,
            ; and this player's eligibility for rested/spouse/bed benefits.
            exhaustionTimestamp.SetValue(Utility.GetCurrentGameTime() * 1440.0)
            SurvivalModeImprovedApi.RestoreExhaustionLevel(remainingRelief)
            LoreRimLANRest.RestExchange(-7.0)
            ; A local menu adapter must check this player's unspent points.
            ; Do not call SSL.UpdateSkillCaps here: it adds a fresh level award.
            SendModEvent("LoreRimLAN_RestCompleted", "", hours)
            localSleep = False
            restSnapshotValid = False
        EndIf
    EndIf
    RegisterForSingleUpdate(1.0)
EndEvent

ScriptName SkyrimTogetherPlayerAliasScript extends ReferenceAlias

SkyrimTogetherVerifyLaunchScript Property VerifyLaunchScript Auto
; Installed Survival Mode Improved default, configurable in a LAN-only plugin.
Float Property ExhaustionRestoredPerHour = 50.0 Auto
Bool localSleep = False
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
            ; Let the normal sleep quest apply the sleeper's actual benefit first.
            Utility.Wait(0.3)
            PlayerSleepQuestScript sleepQuest = Game.GetFormFromFile(0x000FC1A2, "Skyrim.esm") as PlayerSleepQuestScript
            Int benefit = 0
            If sleepQuest
                If Game.GetPlayer().HasSpell(sleepQuest.MarriageSleepAbility)
                    benefit = 3
                ElseIf Game.GetPlayer().HasSpell(sleepQuest.WellRested)
                    benefit = 2
                ElseIf Game.GetPlayer().HasSpell(sleepQuest.Rested)
                    benefit = 1
                EndIf
            EndIf
            LoreRimLANRest.RestExchange(-10.0 - benefit)
        EndIf
    EndIf
EndEvent

Event OnUpdate()
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
        If hours > 0.0
            ; The sleeper already received the game's normal sleep bookkeeping.
            If !localSleep
                SurvivalModeImprovedApi.RestoreExhaustionLevel(hours * ExhaustionRestoredPerHour)
            EndIf
            Int benefit = LoreRimLANRest.RestExchange(-7.0) as Int
            If !localSleep && benefit > 0
                PlayerSleepQuestScript sleepQuest = Game.GetFormFromFile(0x000FC1A2, "Skyrim.esm") as PlayerSleepQuestScript
                If sleepQuest
                    sleepQuest.RemoveRested()
                    If benefit == 3
                        player.AddSpell(sleepQuest.MarriageSleepAbility, False)
                    ElseIf benefit == 2
                        player.AddSpell(sleepQuest.WellRested, False)
                    ElseIf benefit == 1
                        player.AddSpell(sleepQuest.Rested, False)
                    EndIf
                EndIf
            EndIf
            ; A local menu adapter must check this player's unspent points.
            ; Do not call SSL.UpdateSkillCaps here: it adds a fresh level award.
            SendModEvent("LoreRimLAN_RestCompleted", "", hours)
            localSleep = False
        EndIf
    EndIf
    RegisterForSingleUpdate(1.0)
EndEvent

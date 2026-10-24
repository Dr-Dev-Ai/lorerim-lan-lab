Scriptname LoreRimLANRest Hidden
; 1..24: request leader sleep; -1: completed; -2: interrupted;
; 0: consume the locally pending completed rest hours once.
; -8: snapshot needed; -9: this player's SMI snapshot is ready.
Float Function RestExchange(Float command) Global Native

Int Function NextEquipmentActor() Global Native

; Commands: claim=0, permission=1, follow=2, wait=3, dismiss=4, dead=5.
; Returns pending=0, allowed=1, denied=-1. IDs are Int to retain ESL/runtime bits.
Int Function CampaignFollower(Int actorId, Int command) Global Native

Bool Function FollowerAllowed(Actor follower, Int command = 1) Global
    If !follower
        Return False
    EndIf
    Bool wasOnline = CampaignFollower(0, 6) == 1
    Int attempt = 0
    Int answer = CampaignFollower(follower.GetFormID(), command)
    While answer == 0 && attempt < 80
        Utility.WaitMenuMode(0.1)
        answer = CampaignFollower(follower.GetFormID(), command)
        attempt += 1
    EndWhile
    If wasOnline && CampaignFollower(0, 6) != 1
        Return False
    EndIf
    Return answer == 1
EndFunction

Int Function NextCampaignFollower() Global Native

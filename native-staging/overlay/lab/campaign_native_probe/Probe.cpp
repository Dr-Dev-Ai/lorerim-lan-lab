#include <chrono>
#include <optional>
#include <functional>
#include <TiltedCore/Stl.hpp>
#include <TiltedCore/Allocator.hpp>
#include <TiltedCore/Buffer.hpp>
#include <TiltedCore/ViewBuffer.hpp>
#include <TiltedCore/Serialization.hpp>
#include <glm/vec2.hpp>
#include <glm/vec3.hpp>
#include <Client.hpp>
#include <Packet.hpp>
#include <Messages/AuthenticationRequest.h>
#include <Messages/ServerMessageFactory.h>
#include <Messages/CampaignActionRequest.h>
#include <Messages/AssignCharacterRequest.h>
#include <Messages/NotifyCampaignAction.h>
#include <Messages/NotifyCampaignCheckpoint.h>
#include <Messages/RequestCampaignCheckpoint.h>
#include <set>
#include <BuildInfo.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <thread>
#include <fstream>
#include <iostream>

struct Probe : TiltedPhoques::Client
{
    std::string Mode, Credential, SaveProof, Outbox;
    nlohmann::json Profile;
    std::set<uint64_t> Submitted;
    bool Done{}, Passed{}, Attached{}, WaitingFence{};
    std::chrono::steady_clock::time_point FenceUntil;
    std::chrono::steady_clock::time_point Finish;
    void SendMessage(const ClientMessage& message)
    {
        TiltedPhoques::Buffer buffer(65536);
        TiltedPhoques::Buffer::Writer writer(&buffer);
        writer.WriteBits(0,8);
        message.Serialize(writer);
        TiltedPhoques::PacketView packet(reinterpret_cast<char*>(buffer.GetWriteData()),static_cast<uint32_t>(writer.Size()));
        Client::Send(&packet);
    }
    bool ExpectsAdmission() const { return Mode=="valid" || Mode=="heartbeat" || Mode=="fence" || Mode=="coopsave"; }
    void Attach()
    {
        CampaignActionRequest attach;
        attach.RequestId=1;attach.Action=CampaignAction::Join;
        attach.Credential=Mode=="invalid" ? "invalid-test-credential" : Credential.c_str();
        attach.SaveProof=Mode=="missing_proof" ? "" : SaveProof.c_str();
        SendMessage(attach);
    }
    void OnConnected() override
    {
        AuthenticationRequest request;
        request.Version = BUILD_COMMIT;
        request.Username = "Staged protocol probe";
        request.CampaignGuard = Mode != "disabled";
        request.Level = 1;
        SendMessage(request);
    }
    void OnConsume(const void* data, uint32_t size) override
    {
        TiltedPhoques::ViewBuffer buffer(reinterpret_cast<uint8_t*>(const_cast<void*>(data)),size);
        TiltedPhoques::Buffer::Reader reader(&buffer);
        auto message = ServerMessageFactory{}.Extract(reader);
        if (!message) {Done=true;return;}
        if (message->GetOpcode()==AuthenticationResponse::Opcode)
        {
            const auto* response=static_cast<AuthenticationResponse*>(message.get());
            if (Mode=="disabled")
            { Passed=response->Type==AuthenticationResponse::ResponseType::kClientModsDisallowed;Done=true;return; }
            if (response->Type!=AuthenticationResponse::ResponseType::kAccepted) {Done=true;return;}
            if (Mode=="fence")
            {
                AssignCharacterRequest mutation;mutation.Cookie=0xbad;mutation.ReferenceId={0,0x14};
                SendMessage(mutation);WaitingFence=true;FenceUntil=std::chrono::steady_clock::now()+std::chrono::milliseconds(250);
            }
            else Attach();
        }
        if (Mode=="fence" && message->GetOpcode()==AssignCharacterResponse::Opcode) {Passed=false;Done=true;return;}
        if (Mode=="coopsave" && message->GetOpcode()==NotifyCampaignCheckpoint::Opcode)
        {
            const auto* response=static_cast<NotifyCampaignCheckpoint*>(message.get());
            const auto body=nlohmann::json::parse(response->Payload.c_str(),nullptr,false);
            if(!body.is_object()){Done=true;return;}
            if(body.value("phase","")=="freeze")
            {
                RequestCampaignCheckpoint ready;ready.RequestId=2;
                ready.Payload=nlohmann::json{{"proposal",body["proposal"]},{"action","ready"},{"profile",Profile}}.dump().c_str();SendMessage(ready);
            }
            if(body.value("phase","")=="ack" && !body.value("ok",false)){Done=true;return;}
            if(body.value("phase","")=="resume"){Passed=body.value("committed",false);Done=true;}
        }
        if (message->GetOpcode()==NotifyCampaignAction::Opcode)
        {
            const auto* response=static_cast<NotifyCampaignAction*>(message.get());
            if (Mode=="coopsave")
            {
                if(response->Action==CampaignAction::Join && response->RequestId==1)
                {Attached=response->Allowed; if(!Attached)Done=true;}
                return;
            }
            if(response->Action!=CampaignAction::Join)return;
            Passed=response->RequestId==1 && response->Enabled && response->Allowed==ExpectsAdmission()
                && (!ExpectsAdmission() || response->IsLeader);
            if (Mode=="heartbeat" && Passed) { Attached=true; Finish=std::chrono::steady_clock::now()+std::chrono::seconds(13); }
            else Done=true;
        }
    }
    void OnDisconnected(EDisconnectReason) override {if(!Done)Done=true;}
    void OnUpdate() override {
        if(Mode=="coopsave" && Attached && !Outbox.empty())
        {
            std::ifstream input(Outbox);const auto requests=nlohmann::json::parse(input,nullptr,false);
            if(requests.is_array())for(const auto& row:requests)
            {
                const uint64_t id=row.at("id").get<uint64_t>();
                if(Submitted.insert(id).second)
                {RequestCampaignCheckpoint message;message.RequestId=id;message.Payload=row.at("body").dump().c_str();SendMessage(message);}
            }
        }
 if(WaitingFence && std::chrono::steady_clock::now()>=FenceUntil) { WaitingFence=false;Attach(); } if(Mode=="heartbeat" && Attached && std::chrono::steady_clock::now()>=Finish) Done=true; }
};
int main(int argc,char** argv)
{
    if(argc!=4) {std::cerr<<"Usage: CampaignBridgeProbe endpoint credential-json valid|invalid|disabled|heartbeat\n";return 2;}
    Probe probe;
    probe.Mode=argv[3];
    nlohmann::json credential;
    std::ifstream(argv[2]) >> credential;
    probe.Credential=credential.at("token").get<std::string>();
    auto proof=credential.at("proof");
    if(probe.Mode=="wrong_epoch")proof["epoch"]="00000000-0000-4000-8000-000000000000";
    if(probe.Mode=="wrong_character")proof["character"]="00000000-0000-4000-8000-000000000000";
    if(probe.Mode=="wrong_save")proof["ess_sha256"]=std::string(64,'0');
    if(probe.Mode=="coopsave") {probe.Outbox=credential.at("outbox").get<std::string>();probe.Profile=credential.at("profile");}
    probe.SaveProof=probe.Mode=="invalid_json" ? "not-json" : proof.dump();
    if(!probe.ConnectByIp(argv[1])) return 3;
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(probe.Mode=="coopsave" ? 60 : 25);
    while(!probe.Done && std::chrono::steady_clock::now()<deadline)
    {probe.Update();std::this_thread::sleep_for(std::chrono::milliseconds(10));}
    probe.Close();
    // Pump disconnect cleanup before destroying the connection's event loop.
    for(int i=0;i<5;++i){probe.Update();std::this_thread::sleep_for(std::chrono::milliseconds(10));}
    std::cout<<(probe.Passed ? "PASS: " : "FAIL: ")<<probe.Mode<<" native campaign handshake\n";
    return probe.Passed ? 0 : 1;
}

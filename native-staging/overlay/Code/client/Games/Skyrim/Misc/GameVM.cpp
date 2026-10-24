#include <TiltedOnlinePCH.h>

#include <Misc/GameVM.h>
#include <VersionDb.h>

SkyrimVM* SkyrimVM::Get()
{
    POINTER_SKYRIMSE(SkyrimVM*, s_instance, 400475);

    return *s_instance.Get();
}

BSScript::IVirtualMachine* SkyrimVM::GetVirtualMachine() const noexcept
{
    // Verified against the live 1170 VM and the failing launcher disassembly.
    // 0x210 in 1170 points to IVMDebugInterface, not IVirtualMachine.
    const size_t cOffset = VersionDb::Get().GetLoadedVersionString() == "1.6.1170.0" ? 0x200 : 0x210;
    return *reinterpret_cast<BSScript::IVirtualMachine* const*>(reinterpret_cast<const uint8_t*>(this) + cOffset);
}

bool SkyrimVM::IsInactive() const noexcept
{
    // 1170's VM update (Address Library 53926) reads the freeze byte at
    // +0x680. +0x690 is currentVMMenuModeTime and increases while running.
    const size_t cOffset = VersionDb::Get().GetLoadedVersionString() == "1.6.1170.0" ? 0x680 : 0x690;
    return *reinterpret_cast<const uint32_t*>(reinterpret_cast<const uint8_t*>(this) + cOffset) != 0;
}

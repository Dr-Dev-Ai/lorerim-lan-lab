#pragma once

#include <Misc/BSScript.h>

struct SkyrimVM
{
    virtual ~SkyrimVM();

    static SkyrimVM* Get();

    BSScript::IVirtualMachine* GetVirtualMachine() const noexcept;
    bool IsInactive() const noexcept;

    uint8_t pad8[0x210 - 0x8];
    // 1.7.104 layout only. On 1.6.1170 this slot is IVMDebugInterface.
    // Call GetVirtualMachine() rather than reading this field.
    BSScript::IVirtualMachine* virtualMachine;
    uint8_t pad218[0x690 - 0x218];
    // 1.7.104 layout; use IsInactive() for runtime-specific access.
    int32_t inactive;
};

static_assert(offsetof(SkyrimVM, virtualMachine) == 0x210);
static_assert(offsetof(SkyrimVM, inactive) == 0x690);

using GameVM = SkyrimVM;

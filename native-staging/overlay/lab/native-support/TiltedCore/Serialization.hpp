#pragma once
#include <cstdint>
#include <TiltedCore/Buffer.hpp>
// Declarations only. Serialization sections are not linked by these data tests.
namespace TiltedPhoques {
struct Serialization {
static void WriteVarInt(Buffer::Writer&, uint64_t);
static uint64_t ReadVarInt(Buffer::Reader&);
static void WriteFloat(Buffer::Writer&, float);
static float ReadFloat(Buffer::Reader&);
static void WriteBool(Buffer::Writer&, bool);
static bool ReadBool(Buffer::Reader&);
};
}

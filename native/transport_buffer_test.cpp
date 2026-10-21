#include <Buffer.hpp>
#include <ScratchAllocator.hpp>
#include <fstream>
#include <iostream>
#include <vector>
#include <string>
#include <cstdlib>
#include <cstring>
#include <malloc.h>
namespace TiltedPhoques {
static thread_local Allocator* current;
struct TestHeap final:Allocator {
 void* Allocate(size_t n) noexcept override{return std::malloc(n);}
 void Free(void* p) noexcept override{std::free(p);}
 size_t Size(void* p) noexcept override{return _msize(p);}
};
void Allocator::Set(Allocator* a) noexcept {current=a;}
Allocator* Allocator::Get() noexcept {return current?current:GetDefault();}
Allocator* Allocator::GetDefault() noexcept {static TestHeap h;return &h;}
ScopedAllocator::ScopedAllocator(Allocator* a) noexcept:m_pOldAllocator(Allocator::Get()){Allocator::Set(a);}
ScopedAllocator::ScopedAllocator(Allocator& a) noexcept:ScopedAllocator(&a){}
ScopedAllocator::~ScopedAllocator() noexcept{Allocator::Set(m_pOldAllocator);}
}
using namespace TiltedPhoques;
static bool varint(Buffer::Writer& w,size_t n){do{if(!w.WriteBits(n&127,7)||!w.WriteBits(n>127,1))return false;n>>=7;}while(n);return true;}
static size_t readvar(Buffer::Reader& r){size_t n=0,shift=0;uint64_t b=0,m=0;do{r.ReadBits(b,7);r.ReadBits(m,1);n|=b<<shift;shift+=7;}while(m);return n;}
int main(int argc,char** argv){
 if(argc!=2)return 2;std::ifstream f(argv[1]);std::vector<std::string> names;std::string s;while(std::getline(f,s)){if(!s.empty()&&s.back()=='\r')s.pop_back();if(!s.empty())names.push_back(s);}
 if(names.empty()||names.size()>4096)return 3;
 bool old_failed=false;
 for(bool corrected:{false,true}){
  ScratchAllocator pool(corrected?2*1024*1024:256*1024);ScopedAllocator scope(pool);Buffer b(corrected?256*1024:64*1024);Buffer::Writer w(&b);
  w.WriteBits(names.size(),13);size_t failed=names.size();
  for(size_t i=0;i<names.size();++i){if(!w.WriteBits(i,16)||!w.WriteBits(1,1)||!varint(w,names[i].size())||!w.WriteBytes((const uint8_t*)names[i].data(),names[i].size())){failed=i;break;}}
  if(!corrected){old_failed=failed<names.size();std::cout<<"original first failure entry="<<failed<<" written_bytes="<<w.Size()<<"\n";continue;}
  if(failed!=names.size())return 4;
  Buffer::Reader r(&b);uint64_t n=0;r.ReadBits(n,13);if(n!=names.size())return 5;
  for(size_t i=0;i<n;++i){uint64_t id=0,lite=0;r.ReadBits(id,16);r.ReadBits(lite,1);size_t len=readvar(r);std::string name(len,'\0');if(!r.ReadBytes((uint8_t*)name.data(),len)||id!=i||lite!=1||name!=names[i])return 6;}
  std::cout<<"corrected roundtrip="<<n<<" bytes="<<w.Size()<<" remaining_arena="<<pool.Size(nullptr)<<"\n";
 }
 return old_failed?0:7;
}

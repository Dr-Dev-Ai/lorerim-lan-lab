if is_plat("windows") then
    target("LoreRimCampaignCosave")
        set_kind("shared")
        set_default(false)
        add_files("Plugin.cpp")
        add_includedirs("../../Code/common")
        add_includedirs(os.getenv("LORERIM_SKSE_SDK") or path.join(os.projectdir(), "../build-tools/reference-skse"))
        add_syslinks("ole32")
end
if is_plat("windows") then
    target("CampaignCosaveProbe")
        set_kind("binary")
        set_default(false)
        add_files("Probe.cpp")
        add_includedirs("../../Code/common")
        add_includedirs(os.getenv("LORERIM_SKSE_SDK") or path.join(os.projectdir(), "../build-tools/reference-skse"))
end

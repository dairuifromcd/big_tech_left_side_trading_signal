# 工具链选择

仓库原先无Cloudflare子项目、Wrangler配置或相关依赖；全局cf和wrangler均未发现。

优先评估并采用cf。官方新项目指南使用cloudflare.config.ts及Vite plugin 2 beta，支持DO SQLite class exports、bindings和本地开发；构建不需要凭据，也不上传资源。依据：[cf projects](https://developers.cloudflare.com/cf/projects/)、[first Worker](https://developers.cloudflare.com/cf/get-started/first-worker/)、[config](https://developers.cloudflare.com/cf/projects/cloudflare-config/)。

实际安装cf 1.0.0-beta.29；其npm engines比通用网页更严格，要求Node ^22.23.0 / ^24.22.0 / ^26.12.0。本机原Node 22.17.1不足，因此仅在本子项目安装Node 22.23.0，不升级系统Node。cf --version和cf build已执行成功。

精确依赖版本及传递依赖见cloudflare/package.json和package-lock.json。选择TypeScript纯模块、Node内建test、Node SQLite和官方Miniflare/workerd；没有建立Wrangler配置，没有全局安装。Miniflare 5 API使用其安装包类型核对，避免套用旧版构造参数。

cf build实际委托Vite；workerd本地监听被沙箱拒绝后，通过用户明确批准在沙箱外运行loopback。所有临时、缓存和工具配置目录均指向cloudflare内；运行包装器不继承Token或账户环境变量，不进行登录。安装步骤的npm cache/userconfig/globalconfig亦限定在项目内。

Cloudflare官方DO skill的Wrangler示例用于理解语义，本项目遵照用户要求采用当前cf配置，不机械照搬。直接Miniflare测试覆盖官方workerd及SQLite；未再引入Vitest一套测试框架。cf工具链、SQLite、Cron handler及本地Alarm均有本地验证；远程创建/迁移/运行没有验证。

命令见cloudflare/README.md。不要执行cf deploy、cf init、auth login或任何远程写入命令。

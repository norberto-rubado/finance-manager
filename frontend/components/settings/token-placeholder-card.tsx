import { KeyRound } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function TokenPlaceholderCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5" />
          MCP API Token
        </CardTitle>
        <CardDescription>用于上层 Agent(OpenClaw / Hermes)调用 MCP 工具集</CardDescription>
      </CardHeader>
      <CardContent>
        <Alert>
          <AlertTitle>切片 E 添加</AlertTitle>
          <AlertDescription>
            Token 创建/吊销端点 <code>POST/DELETE /api/admin/tokens</code> 在 slice E
            (MCP server + 部署)中加入。目前 MCP token 通过仓库根 <code>.env</code> 的{' '}
            <code>MCP_API_TOKEN</code> 配置。
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}

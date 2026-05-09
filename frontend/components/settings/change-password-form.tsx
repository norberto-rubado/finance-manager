'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';

const schema = z
  .object({
    old_password: z.string().min(1, '旧密码必填'),
    new_password: z.string().min(8, '新密码至少 8 位'),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ['confirm'],
    message: '两次输入不一致',
  });

type Values = z.infer<typeof schema>;

export function ChangePasswordForm() {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { old_password: '', new_password: '', confirm: '' },
  });

  const onSubmit = async () => {
    // backend 端点 slice E 添加。MVP 路径短:重新生成 ADMIN_PASSWORD_HASH 写 .env 重启即可。
    toast.info(
      '修改密码端点将在 slice E 后启用。当前路径:`.env` 中替换 ADMIN_PASSWORD_HASH 后重启 backend。',
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>修改密码</CardTitle>
        <CardDescription>
          更新登录密码(slice E 后启用 API,现暂改 `.env` 重启生效)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="max-w-sm space-y-4">
            <FormField
              control={form.control}
              name="old_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>当前密码</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="new_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>新密码</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="confirm"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>确认新密码</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit">提交(暂不可用)</Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

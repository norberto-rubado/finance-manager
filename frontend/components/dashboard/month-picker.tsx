'use client';

import { useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';

export interface MonthValue {
  year: number;
  month: number; // 1..12
}

interface Props {
  value: MonthValue;
  onChange: (v: MonthValue) => void;
  /** 从今天往前能选多少个月(含本月),默认 12 */
  monthsBack?: number;
}

/** 返回 (year, month) 加减 delta 月。 */
function shiftMonth(year: number, month: number, delta: number): MonthValue {
  const total = year * 12 + (month - 1) + delta;
  return { year: Math.floor(total / 12), month: (total % 12) + 1 };
}

function labelFor(v: MonthValue, today: MonthValue): string {
  if (v.year === today.year && v.month === today.month) return '本月';
  const last = shiftMonth(today.year, today.month, -1);
  if (v.year === last.year && v.month === last.month) return '上月';
  return `${v.year} 年 ${v.month} 月`;
}

export function MonthPicker({ value, onChange, monthsBack = 12 }: Props) {
  const today = useMemo<MonthValue>(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  }, []);

  const options = useMemo<MonthValue[]>(() => {
    const arr: MonthValue[] = [];
    for (let i = 0; i < monthsBack; i++) {
      arr.push(shiftMonth(today.year, today.month, -i));
    }
    return arr;
  }, [today, monthsBack]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" aria-label="选择月份">
          {labelFor(value, today)}
          <ChevronDown className="ml-2 h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {options.map((o) => (
          <DropdownMenuItem
            key={`${o.year}-${o.month}`}
            onSelect={() => onChange(o)}
          >
            {labelFor(o, today)}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

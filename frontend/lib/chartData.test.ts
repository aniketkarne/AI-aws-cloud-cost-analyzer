import { describe, expect, it } from 'vitest';
import {
  pickLabelKey,
  pickValueKey,
  toChartPoints,
} from '../lib/chartData';

describe('pickValueKey', () => {
  it('prefers the expected key when it has finite values', () => {
    const rows = [
      { service: 'EC2', cost: 12.5, total_cost: 99 },
    ];
    expect(pickValueKey(rows, 'cost')).toBe('cost');
  });

  it('falls back to the first numeric column when the expected key is absent', () => {
    const rows = [{ region: 'us-east-1', total_cost: 42 }];
    expect(pickValueKey(rows, 'cost')).toBe('total_cost');
  });

  it('skips the expected key when every value is null', () => {
    const rows = [
      { cost: null, total_cost: 7 },
      { cost: null, total_cost: 8 },
    ];
    expect(pickValueKey(rows, 'cost')).toBe('total_cost');
  });

  it('returns null when nothing is numeric', () => {
    expect(pickValueKey([{ answer: 'x', sql: 'SELECT 1' }], 'cost')).toBeNull();
    expect(pickValueKey([], 'cost')).toBeNull();
  });

  it('treats numeric strings as numeric', () => {
    expect(pickValueKey([{ cost: '12.5' }], 'cost')).toBe('cost');
  });
});

describe('pickLabelKey', () => {
  it('prefers the expected key when present', () => {
    const rows = [{ service: 'EC2', region: 'us-east-1', cost: 1 }];
    expect(pickLabelKey(rows, 'service', 'cost')).toBe('service');
  });

  it('falls back to a string column and never picks the value column', () => {
    const rows = [{ region: 'us-east-1', total_cost: 42 }];
    expect(pickLabelKey(rows, 'service', 'total_cost')).toBe('region');
    expect(pickLabelKey([{ total_cost: 1 }], 'service', 'total_cost')).toBeNull();
  });
});

describe('toChartPoints', () => {
  it('maps rows with the expected service/cost keys', () => {
    const rows = [
      { service: 'EC2', cost: 12.5 },
      { service: 'S3', cost: 3 },
    ];
    expect(toChartPoints(rows, 'service', 'cost')).toEqual([
      { label: 'EC2', value: 12.5 },
      { label: 'S3', value: 3 },
    ]);
  });

  it('derives columns from LLM-shaped rows (region/total_cost)', () => {
    const rows = [
      { region: 'us-east-1', total_cost: 42.25 },
      { region: 'eu-west-1', total_cost: 17 },
    ];
    expect(toChartPoints(rows, 'service', 'cost')).toEqual([
      { label: 'us-east-1', value: 42.25 },
      { label: 'eu-west-1', value: 17 },
    ]);
  });

  it('drops rows without a finite value instead of charting NaN', () => {
    const rows = [
      { service: 'EC2', cost: 10 },
      { service: 'S3', cost: null },
      { service: 'RDS', cost: Number.NaN },
      { service: 'Lambda', cost: 'not-a-number' },
    ];
    expect(toChartPoints(rows, 'service', 'cost')).toEqual([
      { label: 'EC2', value: 10 },
    ]);
  });

  it('labels rows with a missing label by position', () => {
    const rows = [{ cost: 1 }, { cost: 2 }];
    expect(toChartPoints(rows, 'service', 'cost')).toEqual([
      { label: '#1', value: 1 },
      { label: '#2', value: 2 },
    ]);
  });

  it('returns an empty list when nothing is plottable', () => {
    expect(toChartPoints([], 'service', 'cost')).toEqual([]);
    expect(toChartPoints(null, 'service', 'cost')).toEqual([]);
    expect(toChartPoints('nope', 'service', 'cost')).toEqual([]);
    expect(
      toChartPoints([{ answer: 'text', sql: 'SELECT 1' }], 'service', 'cost')
    ).toEqual([]);
    expect(toChartPoints([{ service: 'EC2', cost: null }], 'service', 'cost')).toEqual([]);
  });

  it('parses numeric strings into chart values', () => {
    expect(
      toChartPoints([{ service: 'EC2', cost: '12.5' }], 'service', 'cost')
    ).toEqual([{ label: 'EC2', value: 12.5 }]);
  });
});

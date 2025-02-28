# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import datetime
import sys
from time import sleep

from bs4 import BeautifulSoup
from nseta.common.commons import *
from nseta.common.history import historicaldata
from nseta.live.live import get_live_quote
from nseta.common.ti import ti
from nseta.common.urls import TICKERTAPE_NEWS_URL
from nseta.resources.resources import *
from nseta.scanner.baseStockScanner import baseStockScanner
from nseta.archives.archiver import *
from nseta.common.log import tracelog, default_logger
from nseta.common.tradingtime import *

__all__ = ['volumeStockScanner']

VOLUME_KEYS = ['TDYVol','FreeFloat','ATR','NATR','TRANGE','Volatility','ATRE-F','ATRE-S','ATRE','Avg7DVol','Remarks','PPoint', 'S1-R3','Symbol', 'Date', 'LTP', 'VWAP', 'Yst%Del', '7DayAvgVolume', 'Yst7DVol(%)', 'TodaysVolume','TDYVol(%)', '7DVol(%)', 'Tdy%Del', 'T0BuySellDiff', '%Change']

class volumeStockScanner(baseStockScanner):
  def __init__(self, indicator='all'):
    super().__init__(indicator=indicator)
    self._keys = ['symbol','previousClose', 'lastPrice', 'deliveryToTradedQuantity', 'BuySellDiffQty', 'totalTradedVolume', 'pChange', 'FreeFloat']

  @property
  def keys(self):
    return self._keys

  @tracelog
  def scan_quanta(self, **kwargs):
    stocks = kwargs['items']
    frames = []
    signalframes = []
    signaldf = None
    tiinstance = ti()
    historyinstance = historicaldata()
    # Time frame you want to pull data from
    start_date = datetime.datetime.now()-datetime.timedelta(days=last_x_days_timedelta())
    arch = archiver()
    end_date = datetime.datetime.now()
    pd.set_option('mode.chained_assignment', None)
    for symbol in stocks:
      df_today = None
      primary = None
      df = None
      try:
        self.update_progress(symbol)
        df = historyinstance.daily_ohlc_history(symbol, start_date, end_date, type=ResponseType.Volume)
        if df is not None and len(df) > 0:
          df = tiinstance.update_ti(df, rsi=True, mom=True, bbands=True, obv=True, macd=True, ema=True, atr=True, pivots=True, trange=True, atre=True, volatility=True, natr=True)
          default_logger().debug(df.to_string(index=False))
          df = df.tail(7)
          primary = arch.restore('{}_live_quote'.format(symbol), ResponseType.Volume)
          if primary is None or len(primary) == 0:
            result, primary = get_live_quote(symbol, keys = self.keys)
          else:
            df_today = primary
          if (primary is not None and len(primary) > 0):
            if df_today is None:
              df_today = pd.DataFrame(primary, columns = ['Updated', 'Symbol', 'Close', 'LTP', 'Tdy%Del', 'T0BuySellDiff', 'TotalTradedVolume','pChange', 'FreeFloat'], index = [''])
              arch.archive(df_today, '{}_live_quote'.format(symbol), ResponseType.Volume)
            df, df_today, signalframes = self.format_scan_volume_df(df, df_today, signalframes)
            frames.append(df)
        else:
          default_logger().debug('Could not fetch daily_ohlc_history for {}'.format(symbol))
      except Exception as e:
        default_logger().debug('Exception encountered for {}'.format(symbol))
        default_logger().debug(e, exc_info=True)
        continue
      except SystemExit:
        sys.exit(1)
    if len(frames) > 0:
      df = pd.concat(frames)
    if len(signalframes) > 0:
      signaldf = pd.concat(signalframes)
    return [df, signaldf]

  def format_scan_volume_df(self, df, df_today, signalframes):
    default_logger().debug(df_today.to_string(index=False))
    signalframescopy = signalframes
    df_today = df_today.tail(1)
    df = df.sort_values(by='Date',ascending=True)
    # Get the 7 day average volume
    total_7day_volume = df.loc[:,'Volume'].sum()
    avg_volume = round(total_7day_volume/7,2)
    n = 1
    if current_datetime_in_ist_trading_time_range():
      # The last record will still be from yesterday
      df = df.tail(n)
    else:
      # When after today's trading session, we want to compare with yesterday's
      # The 2nd last record will be from yesterday
      n = 2
      df = df.tail(n)

    df.loc[:,'FreeFloat'] = np.nan
    df.loc[:,'LTP']=np.nan
    df.loc[:,'%Change'] = np.nan
    df.loc[:,'TDYVol(%)']= np.nan
    df.loc[:,'TDYVol']= np.nan
    df.loc[:,'7DVol(%)'] = np.nan
    df.loc[:,'Remarks']='NA'
    df.loc[:,'Yst7DVol(%)']= np.nan
    df.loc[:,'Avg7DVol'] = np.nan
    df.loc[:,'Yst%Del'] = df.loc[:,'%Deliverable'].apply(lambda x: round(x*100, 1))
    df.loc[:,'Tdy%Del']= np.nan
    df.loc[:,'PPoint']= df.loc[:,'PP']
    df.loc[:,'S1-R3']= np.nan
    

    volume_yest = df.loc[:,'Volume'].iloc[0]
    vwap = df.loc[:,'VWAP'].iloc[n-1]
    df.loc[:,'VWAP'].iloc[n-1] = '₹ {}'.format(vwap)
    ltp = str(df_today.loc[:,'LTP'].iloc[0]).replace(',','')
    ltp = float(ltp)
    symbol = df.loc[:,'Symbol'].iloc[n-1]
    today_volume = float(str(df_today.loc[:,'TotalTradedVolume'].iloc[0]).replace(',',''))
    today_vs_yest = round(100* (today_volume - volume_yest)/volume_yest, 1)
    df.loc[:,'Date'].iloc[n-1] = df_today.loc[:,'Updated'].iloc[0]
    df.loc[:,'%Change'].iloc[n-1] = '{} %'.format(df_today.loc[:,'pChange'].iloc[0])
    freeFloat = df_today.loc[:,'FreeFloat'].iloc[0]
    df.loc[:,'FreeFloat'].iloc[n-1] = freeFloat
    df.loc[:,'Avg7DVol'].iloc[n-1] = avg_volume
    df.loc[:,'TDYVol(%)'].iloc[n-1] = today_vs_yest
    if today_vs_yest >= 100:
      notify(symbol=symbol, title='Volume > Yesterday', message='Volume: {}%'.format(today_vs_yest))
    df.loc[:,'7DVol(%)'].iloc[n-1] = round(100* (today_volume - avg_volume)/avg_volume, 1)
    df.loc[:,'LTP'].iloc[n-1] = '₹ {}'.format(ltp)
    df.loc[:,'Yst7DVol(%)'].iloc[n-1] = round((100 * (volume_yest - avg_volume)/avg_volume), 1)
    df.loc[:,'Tdy%Del'].iloc[n-1] = df_today.loc[:,'Tdy%Del'].iloc[0]
    df.loc[:,'Yst%Del'].iloc[n-1] = df.loc[:,'Yst%Del'].iloc[0]
    df.loc[:,'TDYVol']= today_volume
    r3 = df.loc[:,'R3'].iloc[n-1]
    r2 = df.loc[:,'R2'].iloc[n-1]
    r1 = df.loc[:,'R1'].iloc[n-1]
    pp = df.loc[:,'PP'].iloc[n-1]
    s1 = df.loc[:,'S1'].iloc[n-1]
    s2 = df.loc[:,'S2'].iloc[n-1]
    s3 = df.loc[:,'S3'].iloc[n-1]
    crossover_point = False
    for pt, pt_name in zip([r3,r2,r1,pp,s1,s2,s3], ['R3', 'R2', 'R1', 'PP', 'S1', 'S2', 'S3']):
      # Stocks that are within 0.075% of crossover points
      if abs((ltp-pt)*100/ltp) - resources.scanner().crossover_reminder_percent <= 0:
        crossover_point = True
        df.loc[:,'Remarks'].iloc[n-1]= '** {}'.format(pt_name)
        df.loc[:,'S1-R3'].iloc[n-1] = pt
        break
    if not crossover_point:
      pt_dict = {"R3":r3,"R2":r2,"R1":r1,"PP":pp,"S1":s1,"S2":s2,"S3":s3}
      if ltp <= s3:
        df.loc[:,'Remarks'].iloc[n-1]='LTP < S3'
        df.loc[:,'S1-R3'].iloc[n-1] = s3
      else:
        keys = pt_dict.keys()
        for key in keys:
          pt = pt_dict[key]
          if ltp >= pt:
            df.loc[:,'Remarks'].iloc[n-1]='LTP >= {}'.format(key)
            df.loc[:,'S1-R3'].iloc[n-1] = pt
            break
    if current_datetime_in_ist_trading_time_range():
      df.loc[:,'T0BuySellDiff']= np.nan
      df.loc[:,'T0BuySellDiff'].iloc[n-1] = df_today.loc[:,'T0BuySellDiff'].iloc[0]

    df = df.tail(1)
    default_logger().debug(df.to_string(index=False))
    for key in df.keys():
      # Symbol                  Date     VWAP     LTP %Change  TDYVol(%)  7DVol(%)    Remarks  Yst7DVol(%)  Yst%Del Tdy%Del   PPoint    S1-R3
      if not key in VOLUME_KEYS:
        df.drop([key], axis = 1, inplace = True)
    default_logger().debug(df.to_string(index=False))
    if today_vs_yest > 0 or ltp >= vwap or crossover_point:
      resp = TICKERTAPE_NEWS_URL(symbol.upper())
      bs = BeautifulSoup(resp.text, 'lxml')
      news = ParseNews(soup=bs)
      df.loc[:,'News'] = news.parse_news().ljust(38)
      signalframescopy.append(df)
    return df, df_today, signalframescopy

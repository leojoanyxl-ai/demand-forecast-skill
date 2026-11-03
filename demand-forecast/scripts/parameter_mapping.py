"""Map declared calibration targets to the engine's native coefficients."""
import copy
import itertools
import math
import economic_scenarios as econ


def registry_values(registry):
    values={}
    for key,p in registry['parameters'].items():
        value=p['central'];lo,hi=sorted(p['range'])
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError('参数中央值无效或超出已声明范围：'+key)
        if not p.get('source') or not p.get('interpretation'):raise ValueError('缺少参数出处或解释：'+key)
        if any(not math.isfinite(v) or v<lo or v>hi for v in p['grid']):raise ValueError('网格超出所列参数范围：'+key)
        values[key]=value
    return values


def kappas(config):
    """Local d log TCO / d log purchase price, including the actual tax calculation."""
    step=1e-5;result={}
    for vehicle in ('nev','ice'):
        relief=.5 if vehicle=='nev' else 0
        low=econ.vehicle_cost(config,vehicle,math.exp(-step),relief,1)[0]
        high=econ.vehicle_cost(config,vehicle,math.exp(step),relief,1)[0]
        result[vehicle]=math.log(high/low)/(2*step)
        if result[vehicle]<=0:raise ValueError('购价到持有成本导数非正，检查成本输入。')
    return result


def apply(config,registry,raw=None):
    raw=registry_values(registry) if raw is None else dict(raw)
    a=econ.anchors(config);p=a['share'];k=kappas(config)
    market_k=p*k['nev']+(1-p)*k['ice']
    market_tco=raw['market_purchase_price_elasticity']/market_k
    # Total own-price response includes the M response and the technology-choice response.
    beta=(market_tco*p-raw['nev_purchase_price_elasticity']/k['nev'])/(1-p)
    gamma=raw['infrastructure_sales_elasticity']/(1-p)
    if beta<0:raise ValueError('给定总市场和新能源目标弹性无法产生正向替代系数。')
    mapped={'income_elasticity':raw['income_elasticity'],
            'total_auto_cost_elasticity':market_tco,
            'relative_cost_odds_coefficient':beta,'infrastructure_odds_coefficient':gamma,
            'foreign_demand_elasticity':raw['foreign_demand_elasticity'],
            'export_price_elasticity':raw['export_price_elasticity']}
    for name,value in mapped.items():
        config['parameters'][name].update(value=value,kind='外部量级下条件校准；未本样本识别',
            evidence='统一参数表及转换式见弹性映射.csv；原研究定义/样本迁移仍有限制，不是本项目因果估计。')
    config['parameter_registry']=copy.deepcopy(registry)
    config['mapping_anchor']={'domestic_share':p,'nev_price_to_tco':k['nev'],
                              'ice_price_to_tco':k['ice'],'market_price_to_tco':market_k,'raw':raw}
    return mapped


def grid_points(registry):
    registry_values(registry)
    keys=list(registry['parameters'])
    values=[]
    for key in keys:
        p=registry['parameters'][key]
        values.append(sorted(set(p['grid']+[p['central']]+p['range'])))
    for points in itertools.product(*values):yield dict(zip(keys,points))


def ledger(config,forecasts):
    a=config['mapping_anchor'];p=a['domestic_share'];k=a['nev_price_to_tco'];r=a['raw'];params=config['parameters']
    records=[dict(stage='2026桥接锚点',parameter=key,raw_target=r[key],model_value=params[native]['value'],
        local_implied=implied,formula=formula,status='数学转换已计算；经验迁移未验证') for key,native,implied,formula in [
        ('income_elasticity','income_elasticity',params['income_elasticity']['value'],'直接条件弹性；研究样本迁移待核'),
        ('market_purchase_price_elasticity','total_auto_cost_elasticity',params['total_auto_cost_elasticity']['value']*a['market_price_to_tco'],'epsilon_TCO=epsilon_purchase/kappa_market'),
        ('nev_purchase_price_elasticity','relative_cost_odds_coefficient',k*(params['total_auto_cost_elasticity']['value']*p-params['relative_cost_odds_coefficient']['value']*(1-p)),
         'beta=(epsilon_TCO*w_anchor-epsilon_NEV_purchase/kappa_NEV)/(1-p_anchor)'),
        ('infrastructure_sales_elasticity','infrastructure_odds_coefficient',params['infrastructure_odds_coefficient']['value']*(1-p),'gamma=eta_B/(1-p_anchor)'),
        ('foreign_demand_elasticity','foreign_demand_elasticity',params['foreign_demand_elasticity']['value'],'海外规模代理的条件弹性，非自动等于国外收入弹性'),
        ('export_price_elasticity','export_price_elasticity',params['export_price_elasticity']['value'],'出口需求压力弹性；Armington量级不自动等于该估计量')]]
    for row in forecasts:
        records.append(dict(stage=f"{row['year']}年{row['scenario']}",parameter='infrastructure_sales_elasticity',
            raw_target=r['infrastructure_sales_elasticity'],model_value=params['infrastructure_odds_coefficient']['value'],
            local_implied=(1-row['domestic_share'])*params['infrastructure_odds_coefficient']['value'],
            formula='固定M的局部弹性=(1-p_t)*gamma；固定系数不保证未来销量弹性恒定',status='模型内局部导数，非实证因果贡献'))
    return records

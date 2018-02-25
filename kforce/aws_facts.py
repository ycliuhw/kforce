import boto3  # pragma: no cover

SUBNET_GROUPS = (
    'public',
    'private',
)  # pragma: no cover


def check_rt_internet_facing(facing, route_table):  # pragma: no cover
    assert facing in SUBNET_GROUPS, 'facing has to be in %s' % SUBNET_GROUPS
    routes_facing_igw = [
        route for route in route_table.routes
        if route.state == 'active'
        and route.gateway_id is not None
        and route.gateway_id.startswith('igw-')
    ]  # yapf: disable
    routes_facing_nat = [
        route for route in route_table.routes
        if route.state == 'active'
        and route.nat_gateway_id is not None
        and route.nat_gateway_id.startswith('nat-')
    ]  # yapf: disable
    nat_id = None
    try:
        nat_id = routes_facing_nat[0].nat_gateway_id
    except (AttributeError, IndexError):
        ...
    if facing == 'public':
        return len(routes_facing_igw) > 0, nat_id
    elif facing == 'private':
        return len(routes_facing_igw) == 0 and len(routes_facing_nat) > 0, nat_id  # yapf: disable


def get_vpc_facts(vpc_id):  # pragma: no cover
    ec2_c = boto3.resource('ec2')
    vpc_c = ec2_c.Vpc(id=vpc_id)

    vpc = dict(id=vpc_id, cidr=vpc_c.cidr_block)

    azs = set()
    for facing in SUBNET_GROUPS:
        subnets = set()
        for rt in vpc_c.route_tables.all():
            is_facing_true, nat_id = check_rt_internet_facing(facing, rt)
            if not is_facing_true:
                continue
            for asso in rt.associations:
                if asso.main is True:
                    # ignore main
                    continue
                subnet = asso.subnet
                subnets.add(subnet.id)
                azs.add(subnet.availability_zone)

                vpc['-'.join(['subnet', facing, subnet.availability_zone])] = [subnet.id]
                zone = subnet.availability_zone[-1]
                vpc[zone] = vpc.get(zone, {})
                vpc[zone][facing] = dict(id=subnet.id, cidr=subnet.cidr_block)
                if facing == 'private' and nat_id is not None:
                    vpc[zone][facing]['nat_id'] = nat_id

        vpc['%s_subnets' % facing] = list(subnets)

    return dict(azs=list(azs), vpc=vpc)

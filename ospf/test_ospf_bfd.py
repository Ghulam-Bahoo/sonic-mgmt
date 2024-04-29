import pytest
import logging
import time
import re


logger = logging.getLogger(__name__)


pytestmark = [
    pytest.mark.topology('t0', 't1')
]


def test_ospf_with_bfd(ospf_setup, duthosts, rand_one_dut_hostname):
    setup_info_nbr_addr = ospf_setup['nbr_addr']
    neigh_ip_addrs = list(setup_info_nbr_addr.values())
    duthost = duthosts[rand_one_dut_hostname]

    # Function to configure OSPF on DUT if not already configured
    def configure_ospf(dut_host):
        cmd = 'vtysh -c "show ip ospf neighbor"'
        ospf_neighbors = dut_host.shell(cmd)['stdout'].split("\n")
        ospf_configured = False
        for neighbor in ospf_neighbors:
            if ("ospd is not running" not in neighbor) and (neighbor != "") and ("Neighbor ID" not in neighbor):
                ospf_configured = True
                break

        if not ospf_configured:
            cmd_list = [
                'docker exec -it bgp bash',
                'cd /usr/lib/frr',
                './ospfd &',
                'exit',
                'vtysh',
                'config t',
                'no router bgp',
                'router ospf'
            ]

            for ip_addr in neigh_ip_addrs:
                cmd_list.append('network {}/31 area 0'.format(str(ip_addr)))

            cmd_list.extend([
                'do write',
                'end',
                'exit'
            ])

            dut_host.shell_cmds(cmd_list)
            time.sleep(5)

    # Configure OSPF on DUT
    configure_ospf(duthost)

    # Verify OSPF neighbors
    cmd = 'show ip route ospf'
    ospf_routes = duthost.shell(cmd)['stdout']
    assert "O>" in ospf_routes  # Basic check for OSPF routes

    # Function to enable BFD on OSPF neighbors
    def enable_bfd_on_neighbors(dut_host, neighbor_ips):
        for ip_addr in neighbor_ips:
            cmd_list = [
                'docker exec -it bgp bash',
                'cd /usr/lib/frr',
                './ospfd &',
                './bfdd &',
                'exit',
                'vtysh',
                'config t',
                'bfd',
                f'peer {ip_addr}',
                'exit'
            ]
            dut_host.shell_cmds(cmd_list)

            # Get interface name for the neighbor
            interface_name = get_ospf_neighbor_interfaces(duthost, ip_addr)
            if interface_name:  # Check if interface name is retrieved
                cmd_list = [
                    'cd /usr/lib/frr',
                    './ospfd &',
                    'exit',
                    'vtysh',
                    'config t',
                    f'interface {interface_name}',
                    'ip ospf bfd',
                    'exit'
                ]
                dut_host.shell_cmds(cmd_list)

    # Enable BFD on OSPF neighbors
    enable_bfd_on_neighbors(duthost, neigh_ip_addrs)

    # Function to disable a PortChannel interface
def disable_portchannel(dut_host, neighbor_ip):
    interface_name = get_ospf_neighbor_interfaces(dut_host, neighbor_ip)
    if interface_name:
        cmd = f'sudo config interface {interface_name} shutdown'
        dut_host.shell(cmd)

    else:
        print(f"Interface for OSPF neighbor {neighbor_ip} not found or not PortChannel.")

def verify_ping_after_disable(dut_host, neighbor_ip, expected_failure=True):
    time.sleep(10)  # Wait 10 seconds for routing to adjust
    ping_result = dut_host.shell(f'ping {neighbor_ip}')['stdout']
    
    failure_keywords = ["network unreachable", "host unreachable", "request timed out"]
    success = True
    for keyword in failure_keywords:
        if keyword in ping_result:
            success = False
            break
    
    if expected_failure:
        assert not success, "Test case Passed."
        assert success, "Test case failed."


    # Placeholder definition for get_ospf_neighbor_interfaces function
def get_ospf_neighbor_interfaces(dut_host, neighbor_ip):
    cmd = 'cd /usr/lib/frr && ./ospfd && exit && vtysh -c "show ip ospf neighbor"'
    ospf_neighbor_output = dut_host.shell(cmd)['stdout']

    # Parse the output to find the interface name corresponding to the neighbor IP
    for line in ospf_neighbor_output.split('\n'):
        columns = line.split()
        if neighbor_ip in columns:
            # Check if the interface column contains 'PortChannel'
            if 'PortChannel' in columns[4]:
                return columns[4]  # Return the interface name
    return None  # Return None if interface name is not found or not PortChannel



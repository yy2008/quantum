# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import sqlalchemy as sa
from sqlalchemy.orm import exc

from quantum.db import model_base
from quantum.db import models_v2
from quantum.extensions import agent as ext_agent
from quantum import manager
from quantum.openstack.common import cfg
from quantum.openstack.common import jsonutils
from quantum.openstack.common import log as logging
from quantum.openstack.common import timeutils

LOG = logging.getLogger(__name__)
cfg.CONF.register_opt(
    cfg.IntOpt('agent_down_time', default=5,
               help=_("Seconds to regard the agent is down.")))


class Agent(model_base.BASEV2, models_v2.HasId):
    """Represents agents running in quantum deployments"""

    # L3 agent, DHCP agent, OVS agent, LinuxBridge
    agent_type = sa.Column(sa.String(255), nullable=False)
    binary = sa.Column(sa.String(255), nullable=False)
    # TOPIC is a fanout exchange topic
    topic = sa.Column(sa.String(255), nullable=False)
    # TOPIC.host is a target topic
    host = sa.Column(sa.String(255), nullable=False)
    admin_state_up = sa.Column(sa.Boolean, default=True,
                               nullable=False)
    # the time when first report came from agents
    created_at = sa.Column(sa.DateTime, nullable=False)
    # the time when first report came after agents start
    started_at = sa.Column(sa.DateTime, nullable=False)
    # updated when agents report
    heartbeat_timestamp = sa.Column(sa.DateTime, nullable=False)
    # description is note for admin user
    description = sa.Column(sa.String(255))
    # configurations: a json dict string, I think 4095 is enough
    configurations = sa.Column(sa.String(4095), nullable=False)


class AgentDbMixin(ext_agent.AgentPluginBase):
    """Mixin class to add agent extension to db_plugin_base_v2."""

    def _get_agent(self, context, id):
        try:
            agent = self._get_by_id(context, Agent, id)
        except exc.NoResultFound:
            raise ext_agent.AgentNotFound(id=id)
        return agent

    def _is_agent_down(self, heart_beat_time_str):
        return timeutils.is_older_than(heart_beat_time_str,
                                       cfg.CONF.agent_down_time)

    def _make_agent_dict(self, agent, fields=None):
        attr = ext_agent.RESOURCE_ATTRIBUTE_MAP.get(
            ext_agent.RESOURCE_NAME + 's')
        res = dict((k, agent[k]) for k in attr
                   if k not in ['alive', 'configurations'])
        res['alive'] = not self._is_agent_down(res['heartbeat_timestamp'])
        try:
            res['configurations'] = jsonutils.loads(agent['configurations'])
        except Exception:
            msg = _('Configurations for agent %(agent_type)s on host %(host)s'
                    ' are invalid.')
            LOG.warn(msg, {'agent_type': res['agent_type'],
                           'host': res['host']})
            res['configurations'] = {}
        return self._fields(res, fields)

    def delete_agent(self, context, id):
        with context.session.begin(subtransactions=True):
            agent = self._get_agent(context, id)
            context.session.delete(agent)

    def update_agent(self, context, id, agent):
        agent_data = agent['agent']
        with context.session.begin(subtransactions=True):
            agent = self._get_agent(context, id)
            agent.update(agent_data)
        return self._make_agent_dict(agent)

    def get_agents(self, context, filters=None, fields=None):
        return self._get_collection(context, Agent,
                                    self._make_agent_dict,
                                    filters=filters, fields=fields)

    def _get_agent_by_type_and_host(self, context, agent_type, host):
        query = self._model_query(context, Agent)
        try:
            agent_db = query.filter(Agent.agent_type == agent_type,
                                    Agent.host == host).one()
            return agent_db
        except exc.NoResultFound:
            raise ext_agent.AgentNotFoundByTypeHost(agent_type=agent_type,
                                                    host=host)
        except exc.MultipleResultsFound:
            raise ext_agent.MultipleAgentFoundByTypeHost(agent_type=agent_type,
                                                         host=host)

    def get_agent(self, context, id, fields=None):
        agent = self._get_agent(context, id)
        return self._make_agent_dict(agent, fields)

    def create_or_update_agent(self, context, agent):
        """Create or update agent according to report."""
        with context.session.begin(subtransactions=True):
            res_keys = ['agent_type', 'binary', 'host', 'topic']
            res = dict((k, agent[k]) for k in res_keys)

            configurations_dict = agent.get('configurations', {})
            res['configurations'] = jsonutils.dumps(configurations_dict)
            current_time = timeutils.utcnow()
            try:
                agent_db = self._get_agent_by_type_and_host(
                    context, agent['agent_type'], agent['host'])
                res['heartbeat_timestamp'] = current_time
                if agent.get('start_flag'):
                    res['started_at'] = current_time
                agent_db.update(res)
            except ext_agent.AgentNotFoundByTypeHost:
                res['created_at'] = current_time
                res['started_at'] = current_time
                res['heartbeat_timestamp'] = current_time
                res['admin_state_up'] = True
                agent_db = Agent(**res)
                context.session.add(agent_db)


class AgentExtRpcCallback(object):
    """Processes the rpc report in plugin implementations."""
    RPC_API_VERSION = '1.0'

    def report_state(self, context, **kwargs):
        """Report state from agent to server. """
        agent_state = kwargs['agent_state']['agent_state']
        plugin = manager.QuantumManager.get_plugin()
        plugin.create_or_update_agent(context, agent_state)

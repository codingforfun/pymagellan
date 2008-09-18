"""This module contains a more time efficient version of the rule filter algorithm"""

from osmrules import *

class Node(object):
  nodetype = 'n'
  
  def __init__(self):
    self.children = {} 
    self.elsenode = None   
    self._leaves = []

  @property
  def leaves(self):
    return list(self._leaves)

  def addChild(self, key, child):
    self.children[key] = child
    return child

  def addLeaf(self, leaf):
    self._leaves.append(leaf)

  def getChild(self, key):
    if key in self.children:
      return self.children[key]
    else:
      return None

  def __repr__(self):
    s = ''
    for k,v in self.children.items():
      ss = self.nodetype + '=' + str(k) + ':'
      s += ss
      s += indent(repr(v), len(ss))[len(ss):] + '\n'

    if self.elsenode:
      s += 'else: '+indent(repr(elsenode), len('else:')) + '\n'
    s += str(self.leaves)

    return s

class ElemSelectionNode(Node):
  nodetype = 'e'
  def lookup(self, elem, tags):
    if elem in self.children:
      return self.leaves + (self.children[elem].lookup(elem, tags))
    else:
      return self.leaves

class KeySelectionNode(Node):
  nodetype = 'k'
  def lookup(self, elem, tags):
    result = self.leaves
    for key in Set(tags.keys()) & Set(self.children.keys()):
      result.extend(self.children[key].lookup(elem, tags))
    return result

class ValueSelectionNode(Node):
  nodetype = 'v'
  def addChild(self, value, child, key):
    self.children[value] = child
    self.key = key
    return child

  def lookup(self, elem, tags):
    if tags[self.key] in self.children:
      return self.leaves + self.children[tags[self.key]].lookup(elem,tags)
    return self.leaves

def buildTree(rules):
  """Build search tree

  >>> t = ElementTree(file='test/data/osmmap.xml')
  >>> tree = buildTree(t.find('rules'))
  >>> [e.tag for e in tree.lookup('way', {u'highway': u'motorway', 'apa':'abc'})]
  ['name', 'name', 'polyline']
  >>> [e.tag for e in tree.lookup('node', {u'highway': u'motorway', 'apa':'123'})]
  ['name', 'name']
  >>> [e.tag for e in tree.lookup('way', {u'highway': u'undef', 'apa':'123'})]
  ['name', 'name']
  
  """
  root = ElemSelectionNode()
  
  lastruleelem = None
  for ruleelem in rules.getchildren():
    if ruleelem.tag == 'rule':
      keynode = root.getChild(ruleelem.get("e")) or root.addChild(ruleelem.get("e"), KeySelectionNode())

      keys = ruleelem.get('k').split('|')
      values = ruleelem.get('v').split('|')

      newtree = buildTree(ruleelem)
      for key in keys:
        valuenode = keynode.getChild(key) or keynode.addChild(key, ValueSelectionNode())
        for value in values:
          valuenode.addChild(value, newtree, key)
        
    elif ruleelem.tag == 'else':
      pass
#      if lastruleelem and lastruleelem.tag == 'rule':
#         root.getChild(lastruleelem.tagself.elsenode = buildTree(ruleelem)
#      else:
#        raise ValueError('else clause must be preceeded by rule')
    else:
      root.addLeaf(ruleelem)
    lastruleelem = ruleelem

  return root


class OSMMagRulesFast(OSMMagRules):
    def __init__(self, filename):
        super(OSMMagRulesFast, self).__init__(filename)
        
        self.searchtree = buildTree(self.root.find('rules'))

    def filterOSMElement(self, elem, tags):
        elements = self.searchtree.lookup(elem, tags)
        if len(elements) == 0:
          return None

        result = Element('result')
        for element in elements:
          result.append(element)

        return result



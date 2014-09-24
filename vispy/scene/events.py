# -*- coding: utf-8 -*-
# Copyright (c) 2014, Vispy Development Team.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.

from __future__ import division

from ..util.event import Event
from ..visuals.transforms import TransformCache, TransformSystem


class SceneEvent(Event, TransformSystem):
    """
    SceneEvent is an Event that tracks its path through a scenegraph,
    beginning at a Canvas. It exposes information useful during drawing
    and user interaction.
    """

    def __init__(self, type, canvas, transform_cache=None):
        Event.__init__(self, type=type)
        TransformSystem.__init__(self, canvas)

        # Init stacks
        self._stack = []  # list of entities
        self._stack_ids = set()
        self._viewbox_stack = []
        self._doc_stack = []
        if transform_cache is None:
            transform_cache = TransformCache()
        self._transform_cache = transform_cache

    @property
    def canvas(self):
        """ The Canvas that originated this SceneEvent
        """
        return self._canvas

    @property
    def viewbox(self):
        """ The current viewbox.
        """
        if len(self._viewbox_stack) > 0:
            return self._viewbox_stack[-1]
        else:
            return None

    @property
    def path(self):
        """ The path of Entities leading from the root SubScene to the
        current recipient of this Event.
        """
        return self._stack

    def push_node(self, node):
        """ Push an node on the stack. """
        self._stack.append(node)
        if id(node) in self._stack_ids:
            raise RuntimeError("Scenegraph cycle detected; cannot push %r" % 
                               node)
        self._stack_ids.add(id(node))
        doc = node.document
        if doc is not None:
            self.push_document(doc)

    def pop_node(self):
        """ Pop an node from the stack. """
        ent = self._stack.pop(-1)
        self._stack_ids.remove(id(ent))
        if ent.document is not None:
            assert ent.document == self.pop_document()
        return ent

    def push_viewbox(self, viewbox):
        self._viewbox_stack.append(viewbox)

    def pop_viewbox(self):
        return self._viewbox_stack.pop(-1)

    def push_document(self, doc):
        self._doc_stack.append(doc)

    def pop_document(self):
        return self._doc_stack.pop(-1)

    def push_viewport(self, viewport):
        """ Push a viewport (x, y, w, h) on the stack. It is the
        responsibility of the caller to ensure the given values are
        int. The viewport's origin is defined relative to the current
        viewport.
        """
        self.canvas.push_viewport(viewport)

    def pop_viewport(self):
        """ Pop a viewport from the stack.
        """
        return self.canvas.pop_viewport()

    def push_fbo(self, viewport, fbo, transform):
        """ Push an FBO on the stack, together with the new viewport.
        and the transform to the FBO.
        """
        self.canvas.push_fbo(viewport, fbo, transform)

    def pop_fbo(self):
        """ Pop an FBO from the stack.
        """
        return self.canvas.pop_fbo()

    #
    # Begin transforms
    #

    @property
    def document_cs(self):
        """ The node for the current document coordinate system. The
        coordinate system of this Node is used for making physical
        measurements--px, mm, in, etc.
        """
        if len(self._doc_stack) > 0:
            return self._doc_stack[-1]
        else:
            return self.canvas_cs

    @property
    def canvas_cs(self):
        """ The node for the current canvas coordinate system. This cs 
        represents the logical pixels of the canvas being drawn, with the 
        origin in upper-left, and the canvas (width, height) in the bottom 
        right. This coordinate system is most often used for handling mouse
        input.
        """
        return self.canvas.canvas_cs

    @property
    def buffer_cs(self):
        """ The node for the current framebuffer coordinate system. This
        coordinate system corresponds to the physical pixels being rendered
        to, with the origin in lower-right, and the framebufer (width, height)
        in upper-left. It is used mainly for making antialiasing measurements.
        """
        return self.canvas.buffer_cs

    @property
    def render_cs(self):
        """ Return node for the normalized device coordinate system. This
        coordinate system is the obligatory output of GLSL vertex shaders, 
        with (-1, -1) in bottom-left, and (1, 1) in top-right. This coordinate
        system is frequently used for rendering visuals because all vertices
        must ultimately be mapped here.
        """
        return self.canvas.render_cs

    @property
    def visual_to_document(self):
        """ Transform mapping from visual local coordinate frame to document
        coordinate frame.
        """
        return self.node_transform(map_to=self.document_cs, map_from=node)
        
    @visual_to_document.setter
    def visual_to_document(self, tr):
        raise RuntimeError("Cannot set transforms on SceneEvent.")
        
    @property
    def document_to_buffer(self):
        """ Transform mapping from document coordinate frame to the framebuffer
        (physical pixel) coordinate frame.
        """
        return self.node_transform(map_to=self.buffer_cs, 
                                   map_from=self.document_cs)
        
    @document_to_buffer.setter
    def document_to_buffer(self, tr):
        raise RuntimeError("Cannot set transforms on SceneEvent.")
        
    @property
    def buffer_to_render(self):
        """ Transform mapping from pixel coordinate frame to rendering
        coordinate frame.
        """
        return self.node_transform(map_to=self.render_cs, 
                                   map_from=self.buffer_cs)

    @buffer_to_render.setter
    def buffer_to_render(self, tr):
        raise RuntimeError("Cannot set transforms on SceneEvent.")

    def get_full_transform(self):
        """ Return the transform that maps from the current node to
        normalized device coordinates within the current glViewport and
        FBO.

        This transform consists of the full_transform prepended by a
        correction for the current glViewport and/or FBO.

        Most entities will use this transform when drawing.
        """
        return self._transform_cache.get([e.transform for e in self._stack])

    @property
    def scene_transform(self):
        """ The transform that maps from the current node to the first
        scene in its ancestry.
        """
        if len(self._viewbox_stack) > 1:
            view = self._viewbox_stack[-1]
            return self.node_transform(map_to=view.scene)
        else:
            return None

    @property
    def view_transform(self):
        """ The transform that maps from the current node to the first
        viewbox in its ancestry.
        """
        if len(self._viewbox_stack) > 1:
            view = self._viewbox_stack[-1]
            return self.node_transform(map_to=view)
        else:
            return None

    def node_transform(self, map_to=None, map_from=None):
        """ Return the transform from *map_from* to *map_to*, using the
        current node stack to resolve parent ambiguities if needed.

        By default, *map_to* is the normalized device coordinate system,
        and *map_from* is the current top node on the stack.
        """
        if map_to is None:
            map_to = self.render_cs
        if map_from is None:
            map_from = self._stack[-1]

        fwd_path = self._node_path(map_from, map_to)
        fwd_path.reverse()

        if fwd_path[0] is map_to:
            rev_path = []
            fwd_path = fwd_path[1:]
        else:
            # If we have still not reached the end, try traversing from the
            # opposite end and stop when paths intersect
            rev_path = self._node_path(map_to, self._stack[0])
            connected = False
            for i in range(1, len(rev_path)):
                if rev_path[i] in fwd_path:
                    rev_path = rev_path[:i]
                    connected = True

            if not connected:
                raise RuntimeError("Unable to find unique path from %r to %r" %
                                   (map_from, map_to))

        transforms = ([e.transform for e in fwd_path] +
                      [e.transform.inverse for e in rev_path])
        return self._transform_cache.get(transforms)

    def _node_path(self, start, end):
        """
        Return the path of parents leading from *start* to *end*, using the
        node stack to resolve multi-parent branches.

        If *end* is never reached, then the path is assembled as far as
        possible and returned.
        """
        path = [start]

        # first, get parents directly from node
        node = start
        while id(node) not in self._stack_ids:
            if node is end or len(node.parents) != 1:
                return path
            node = node.parent
            path.append(node)

        # if we have not reached the end, follow _stack if possible.
        if path[-1] is not end:
            try:
                ind = self._stack.index(node)
                # copy stack onto path one node at a time
                while ind > -1 and path[-1] is not end:
                    ind -= 1
                    path.append(self._stack[ind])
            except IndexError:
                pass

        return path


class SceneDrawEvent(SceneEvent):
    def __init__(self, event, canvas, **kwds):
        self.draw_event = event
        super(SceneDrawEvent, self).__init__(type='draw', canvas=canvas,
                                             **kwds)


class SceneMouseEvent(SceneEvent):
    """ Represents a mouse event that occurred on a SceneCanvas. This event is
    delivered to all entities whose mouse interaction area is under the event. 
    """
    def __init__(self, event, canvas, **kwds):
        self.mouse_event = event
        super(SceneMouseEvent, self).__init__(type=event.type, canvas=canvas,
                                              **kwds)

    @property
    def pos(self):
        """ The position of this event in the local coordinate system of the 
        visual.
        """
        return self.map_from_canvas(self.mouse_event.pos)

    @property
    def last_event(self):
        """ The mouse event immediately prior to this one. This
        property is None when no mouse buttons are pressed.
        """
        if self.mouse_event.last_event is None:
            return None
        ev = self.copy()
        ev.mouse_event = self.mouse_event.last_event
        return ev

    @property
    def press_event(self):
        """ The mouse press event that initiated a mouse drag, if any. 
        """
        if self.mouse_event.press_event is None:
            return None
        ev = self.copy()
        ev.mouse_event = self.mouse_event.press_event
        return ev

    @property
    def button(self):
        """ The button pressed or released on this event.
        """
        return self.mouse_event.button

    @property
    def buttons(self):
        """ A list of all buttons currently pressed on the mouse.
        """
        return self.mouse_event.buttons

    @property
    def delta(self):
        """ The increment by which the mouse wheel has moved.
        """
        return self.mouse_event.delta

    def copy(self):
        ev = self.__class__(self.mouse_event, self._canvas)
        ev._stack = self._stack[:]
        #ev._ra_stack = self._ra_stack[:]
        ev._viewbox_stack = self._viewbox_stack[:]
        return ev
